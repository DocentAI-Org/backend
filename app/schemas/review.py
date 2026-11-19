import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.types import FlagCategory
from app.schemas.chat import Citation, StudentMessage
from app.schemas.common import CleanText
from app.schemas.exercises import StudentSubmission


class FlagUpsert(BaseModel):
    category: FlagCategory
    correction: CleanText = Field(min_length=1, max_length=4000)


class TeacherFlag(BaseModel):
    id: uuid.UUID
    category: FlagCategory
    correction: str
    author_name: str | None
    created_at: datetime
    updated_at: datetime


class TeacherMessage(StudentMessage):
    flag: TeacherFlag | None


class ConversationSummary(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    started_at: datetime
    last_message_at: datetime
    message_count: int
    has_no_source: bool
    has_correction: bool


class TeacherConversation(ConversationSummary):
    messages: list[TeacherMessage]


class TeacherSubmission(StudentSubmission):
    student_id: uuid.UUID
    student_name: str
    flag: TeacherFlag | None


class EvaluationItem(BaseModel):
    flag_id: uuid.UUID
    course_id: uuid.UUID
    category: FlagCategory
    correction: str
    question: str
    original_answer: str
    citations: list[Citation]
    created_at: datetime


class CourseFlag(TeacherFlag):
    student_id: uuid.UUID
    student_name: str
    original_text: str = Field(description="The tutor answer or feedback corrected.")
    target: Literal["message", "submission"]
    conversation_id: uuid.UUID | None
    message_id: uuid.UUID | None
    submission_id: uuid.UUID | None
