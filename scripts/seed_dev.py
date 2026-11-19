"""Creates demo users in the LOCAL Supabase stack and prints access tokens.

    uv run python scripts/seed_dev.py

Local development only: it refuses to run against a non-local SUPABASE_URL.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.core.errors import ApiError  # noqa: E402
from app.core.types import Role  # noqa: E402
from app.integrations.auth_admin import SupabaseAuthAdmin  # noqa: E402
from app.models import Profile  # noqa: E402

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


def main() -> int:
    settings = get_settings()
    if urlparse(settings.supabase_url).hostname not in {"127.0.0.1", "localhost"}:
        print("Refusing to seed a non-local Supabase project.", file=sys.stderr)
        return 1
    auth_admin = SupabaseAuthAdmin(settings)
    with get_session_factory()() as session:
        for role, email, name in USERS:
            try:
                auth_admin.create_user(email, PASSWORD, name)
            except ApiError as error:
                if error.code != "email_taken":
                    raise
            profile = session.scalar(select(Profile).where(Profile.email == email))
            assert profile is not None, f"No profile for {email}"
            profile.role = role
        session.commit()

    # The password stays out of the output; it is PASSWORD at the top of this file.
    print("Demo users share the password in PASSWORD, scripts/seed_dev.py.\n")
    for role, email, _ in USERS:
        print(f"{role.upper()}={sign_in(email)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
