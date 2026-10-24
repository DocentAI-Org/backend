"""Account provisioning by admins (FR-013, FR-014, research R8)."""

import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations.auth_admin import AuthAdminClient
from app.models import Course, Enrolment, Profile
from app.schemas.admin import AdminCourse, PseudonymousAccount

# No ambiguous characters (0/O, 1/I/L) so codes can be read aloud or copied by hand.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def random_code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def generate_password() -> str:
    return secrets.token_urlsafe(12)


def _load_profile(session: Session, user_id: uuid.UUID) -> Profile:
    session.expire_all()
    profile = session.get(Profile, user_id)
    if profile is None:
        raise ApiError(503, "auth_unavailable", "The new account has no profile.")
    return profile


def create_teacher(
    session: Session,
    auth_admin: AuthAdminClient,
    email: str,
    display_name: str,
    password: str | None,
) -> tuple[Profile, str]:
    initial_password = password or generate_password()
    user_id = auth_admin.create_user(email.lower(), initial_password, display_name)
    profile = _load_profile(session, user_id)
    profile.role = "teacher"
    profile.display_name = display_name
    session.flush()
    return profile, initial_password


def create_pseudonymous_students(
    session: Session, auth_admin: AuthAdminClient, settings: Settings, count: int
) -> list[PseudonymousAccount]:
    accounts: list[PseudonymousAccount] = []
    for _ in range(count):
        code = _unused_pseudonym_code(session)
        password = generate_password()
        email = f"{code.lower()}@{settings.pseudonym_email_domain}"
        user_id = auth_admin.create_user(email, password, code)
        profile = _load_profile(session, user_id)
        profile.pseudonym_code = code
        profile.display_name = code
        # The synthetic auth email is not personal data and is not shown anywhere.
        profile.email = None
        session.flush()
        accounts.append(
            PseudonymousAccount(user_id=user_id, code=code, initial_password=password)
        )
    return accounts


def _unused_pseudonym_code(session: Session) -> str:
    while True:
        code = f"EST-{random_code(5)}"
        taken = session.scalar(select(Profile.id).where(Profile.pseudonym_code == code))
        if taken is None:
            return code


def list_users(
    session: Session, role: str | None, status: str | None, limit: int, offset: int
) -> tuple[list[Profile], int]:
    query = select(Profile)
    if role:
        query = query.where(Profile.role == role)
    if status:
        query = query.where(Profile.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Profile.created_at.desc(), Profile.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def list_courses(
    session: Session, limit: int, offset: int
) -> tuple[list[AdminCourse], int]:
    total = session.scalar(select(func.count(Course.id))) or 0
    student_count = (
        select(func.count(Enrolment.id))
        .where(Enrolment.course_id == Course.id, Enrolment.status == "active")
        .scalar_subquery()
    )
    rows = session.execute(
        select(Course, student_count)
        .order_by(Course.created_at.desc(), Course.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        AdminCourse(
            id=course.id,
            name=course.name,
            teacher_name=course.teacher.display_name,
            student_count=count,
            created_at=course.created_at,
        )
        for course, count in rows
    ]
    return items, total
