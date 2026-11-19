import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.types import AccountStatus, Role
from app.models import Profile
from app.schemas.common import ApiModel


class AdminUser(ApiModel):
    id: uuid.UUID
    role: Role
    display_name: str
    email: str | None
    is_pseudonymous: bool
    status: AccountStatus
    created_at: datetime

    @classmethod
    def from_profile(cls, profile: Profile) -> "AdminUser":
        return cls(
            id=profile.id,
            role=profile.role,
            display_name=profile.display_name,
            email=profile.email,
            is_pseudonymous=profile.pseudonym_code is not None,
            status=profile.status,
            created_at=profile.created_at,
        )


class TeacherCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    password: str | None = Field(default=None, min_length=12, max_length=128)


class CreatedAccount(BaseModel):
    user: AdminUser
    initial_password: str = Field(description="Shown once; the API does not store it.")


class PseudonymousBatchCreate(BaseModel):
    count: int = Field(ge=1, le=100)


class PseudonymousAccount(BaseModel):
    user_id: uuid.UUID
    code: str
    initial_password: str


class PseudonymousBatch(BaseModel):
    accounts: list[PseudonymousAccount]


class AdminCourse(BaseModel):
    id: uuid.UUID
    name: str
    teacher_name: str
    student_count: int
    created_at: datetime


class StudentErasure(BaseModel):
    """What an erasure deleted (spec 017); nothing about the student is kept."""

    student_id: uuid.UUID
    courses: int = Field(description="Enrolments deleted")
    conversations: int
    messages: int
    exercise_submissions: int
    quizzes: int
    test_attempts: int
    interaction_logs: int
