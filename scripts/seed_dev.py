"""Seeds the LOCAL stack with sample data and prints access tokens.

    uv run python scripts/seed_dev.py            # creates the sample data once
    uv run python scripts/seed_dev.py --reset    # deletes the sample courses first

Creates the admin, four teachers and three class groups of students (scripts/seed_data/,
shared with the frontend's demo deployment), twelve courses of several subjects with
their material, topics, question bank and pre/post tests, and about eight weeks of
student activity dated relative to now. The demo accounts are:

    admin@docentai.local       admin
    profesora@docentai.local   Prof. Elena Ruiz (Matemáticas)
    alumno@docentai.local      Lucas Herrera (3º ESO B), at risk in Álgebra

Every sample account shares the password in PASSWORD. The material is uploaded and
processed by the app itself, so Ollama must serve the embedding model. Running it again
creates nothing while the sample courses exist (users are reused); `--reset` deletes
those courses, their files and everything linked to them, and builds them again.

Local development only: it refuses to run against a non-local SUPABASE_URL.
"""

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.core.errors import ApiError  # noqa: E402
from app.core.types import Role  # noqa: E402
from app.integrations.auth_admin import SupabaseAuthAdmin  # noqa: E402
from app.integrations.storage import StorageError, get_storage  # noqa: E402
from app.llm.client import LLMClient, get_llm  # noqa: E402
from app.models import Course, Document, Profile  # noqa: E402
from scripts.seed_activity import CourseSeed, Seeder  # noqa: E402
from scripts.seed_material import COURSE_KEYS, people  # noqa: E402

PASSWORD = "docentai-dev-password"  # noqa: S105 (local demo users only)
USERS: list[tuple[Role, str, str]] = [
    ("admin", "admin@docentai.local", "Admin DocentAI"),
    ("teacher", "profesora@docentai.local", "Prof. Elena Ruiz"),
    ("student", "alumno@docentai.local", "Lucas Herrera"),
]


def sign_in(email: str) -> str:
    settings = get_settings()
    key = settings.supabase_service_role_key or ""
    response = httpx.post(
        f"{settings.supabase_url}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": key},
        json={"email": email, "password": PASSWORD},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def account(
    session: Session, auth_admin: SupabaseAuthAdmin, email: str, name: str
) -> Profile:
    """The profile of the auth account with this email, created if missing."""
    try:
        auth_admin.create_user(email, PASSWORD, name)
    except ApiError as error:
        if error.code != "email_taken":
            raise
    user_id = session.scalar(
        text("select id from auth.users where email = :email"), {"email": email}
    )
    profile = session.get(Profile, user_id, populate_existing=True)
    assert profile is not None, f"No profile for {email}"
    return profile


def seed_users(
    session: Session, settings: Settings, seeder: Seeder
) -> dict[str, Profile]:
    """Every sample account by email, with its role and profile set."""
    auth_admin = SupabaseAuthAdmin(settings)
    roster = people()
    users: dict[str, Profile] = {}
    wanted: list[tuple[Role, dict[str, Any], float]] = [
        ("admin", {"email": USERS[0][1], "name": USERS[0][2]}, 75),
        *[("teacher", t, 74) for t in roster["teachers"]],
        *[("student", s, 70) for g in roster["groups"] for s in g["students"]],
    ]
    for role, person, days in wanted:
        if person["email"] in users:
            continue
        profile = account(session, auth_admin, person["email"], person["name"])
        profile.role = role
        profile.display_name = person["name"]
        profile.created_at = seeder.days_ago(days)
        if person.get("pseudonym"):
            # As the app creates them (app/services/accounts.py): the synthetic auth
            # email is not personal data and is not kept on the profile.
            profile.pseudonym_code = person["pseudonym"]
            profile.email = None
        users[person["email"]] = profile
    session.commit()
    return users


def reset(session: Session, codes: list[str]) -> int:
    """Deletes the sample courses; the database cascades to everything linked."""
    storage = get_storage()
    courses = list(
        session.scalars(select(Course.id).where(Course.class_code.in_(codes)))
    )
    for path in session.scalars(
        select(Document.storage_path).where(Document.course_id.in_(courses))
    ):
        try:
            storage.delete(path)
        except StorageError:
            print(f"Could not delete the stored file {path}.", file=sys.stderr)
    session.execute(delete(Course).where(Course.id.in_(courses)))
    session.commit()
    return len(courses)


def check_embeddings(llm: LLMClient) -> bool:
    try:
        llm.embed(["comprobación"])
    except Exception as exc:  # any failure means the material cannot be processed
        print(
            f"Embeddings are unavailable ({exc.__class__.__name__}). Start Ollama and "
            "pull the embedding model (`ollama pull bge-m3`), or check LLM_* in .env.",
            file=sys.stderr,
        )
        return False
    return True


def seed_courses(seeder: Seeder, users: dict[str, Profile]) -> None:
    roster = people()
    teachers = {t["key"]: users[t["email"]] for t in roster["teachers"]}
    groups = {
        g["key"]: [users[s["email"]] for s in g["students"]] for g in roster["groups"]
    }
    # One student left the university group: account disabled, places revoked.
    leaver = groups["uni"][-1]
    leaver.status = "disabled"
    metas = {c["key"]: c for c in roster["courses"]}
    courses: dict[str, CourseSeed] = {}
    for index, key in enumerate(COURSE_KEYS):
        meta = metas[key]
        print(f"  {key}…", flush=True)
        courses[key] = seeder.course(
            index, key, teachers[meta["teacher"]], groups[meta["group"]], leaver
        )
    seeder.tags_and_favorites(courses, users)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seeds the local stack with sample data."
    )
    parser.add_argument(
        "--reset", action="store_true", help="delete the sample courses first"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    if urlparse(settings.supabase_url).hostname not in {"127.0.0.1", "localhost"}:
        print("Refusing to seed a non-local Supabase project.", file=sys.stderr)
        return 1
    llm = get_llm()
    codes = [c["class_code"] for c in people()["courses"]]
    with get_session_factory()() as session:
        if args.reset:
            print(f"Deleted {reset(session, codes)} sample courses.")
        seeded = session.scalar(select(Course.id).where(Course.class_code.in_(codes)))
        if seeded is None and not check_embeddings(llm):
            return 1
        seeder = Seeder(session, settings, llm, get_storage())
        users = seed_users(session, settings, seeder)
        if seeded is None:
            print("Creating the sample courses and activity:")
            seed_courses(seeder, users)
        else:
            print("The sample courses exist already (--reset builds them again).")

    # The password stays out of the output; it is PASSWORD at the top of this file.
    print("Demo users share the password in PASSWORD, scripts/seed_dev.py.\n")
    for role, email, _ in USERS:
        print(f"{role.upper()}={sign_in(email)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
