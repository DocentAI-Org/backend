"""Tags of one's own on courses (specs/016 US4)."""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.schemas.common import CleanText
from app.schemas.courses import TagColor


def _trimmed(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("The name cannot be empty.")
    return value


TagName = Annotated[CleanText, Field(max_length=40), AfterValidator(_trimmed)]


class CourseTagCreate(BaseModel):
    name: TagName
    color: TagColor


class CourseTagUpdate(BaseModel):
    name: TagName | None = None
    color: TagColor | None = None


class CourseTag(BaseModel):
    id: uuid.UUID
    name: str
    color: TagColor
    course_count: int = Field(
        description="Courses the user teaches or is in with this tag."
    )
