import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.types import EnrolmentStatus, TagColor
from app.schemas.common import CleanText


class CourseCreate(BaseModel):
    name: CleanText = Field(min_length=1, max_length=80)
    description: CleanText | None = Field(default=None, max_length=500)


class CourseUpdate(BaseModel):
    name: CleanText | None = Field(default=None, min_length=1, max_length=80)
    description: CleanText | None = Field(default=None, max_length=500)


class ClassCodeUpdate(BaseModel):
    active: bool


class CourseTagRef(BaseModel):
    """One of the caller's tags on a course (specs/016 US4)."""

    id: uuid.UUID
    name: str
    color: TagColor


class TeacherCourse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    class_code: str
    class_code_active: bool
    invitation_path: str = Field(description="Frontend path; prefix with its origin.")
    student_count: int
    created_at: datetime
    is_favorite: bool = Field(
        default=False, description="Starred by the caller; listed first (specs/016)."
    )
    tags: list[CourseTagRef] = Field(
        default_factory=list, description="The caller's own tags (specs/016 US4)."
    )


class CourseStudent(BaseModel):
    student_id: uuid.UUID
    display_name: str
    joined_at: datetime
    status: EnrolmentStatus


class JoinCourse(BaseModel):
    class_code: str = Field(min_length=1, max_length=20)


class StudentCourse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    teacher_name: str
    joined_at: datetime
    disclosure_acknowledged: bool
    is_favorite: bool = Field(
        default=False, description="Starred by the caller; listed first (specs/016)."
    )
    tags: list[CourseTagRef] = Field(
        default_factory=list, description="The caller's own tags (specs/016 US4)."
    )
