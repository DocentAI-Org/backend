import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import CleanText

MessageKind = Literal["question", "answer", "hint", "no_source"]


class MessageCreate(BaseModel):
    text: CleanText = Field(min_length=1, max_length=4000)
    request_solution: bool = Field(
        default=False, description="Ask for the full solution (policy permitting)."
    )


class Citation(BaseModel):
    fragment_id: uuid.UUID | None
    document_name: str
    location_label: str
    passage: str | None = Field(description="Withheld when no longer available.")
    available: bool


class Correction(BaseModel):
    text: str
    reviewed_at: datetime


class Adaptation(BaseModel):
    """Why an explanation was adapted (specs/013): shown to the student and teacher."""

    error_type: str = Field(description="Error type code the student repeats.")
    count: int = Field(description="Mistakes of that type in the window.")
    window_days: int


class StudentMessage(BaseModel):
    id: uuid.UUID
    author: Literal["student", "tutor"]
    kind: MessageKind
    status: Literal["sent", "failed"]
    text: str
    hint_number: int | None
    request_solution: bool
    counts_toward_limit: bool
    created_at: datetime
    citations: list[Citation]
    correction: Correction | None
    adaptation: Adaptation | None = Field(
        default=None, description="Set when the answer was adapted (specs/013)."
    )


class Allowance(BaseModel):
    """The tighter of the course's limit and the daily ceiling across courses
    (specs/019); a null limit is no limit."""

    scope: Literal["course", "daily"]
    limit: int | None
    used: int
    remaining: int | None
    period: Literal["day", "week", "course"]
    resets_at: datetime | None = Field(description="Null for a whole-course limit.")


class TutorExchange(BaseModel):
    student_message: StudentMessage
    tutor_message: StudentMessage
    allowance: Allowance


class Conversation(BaseModel):
    id: uuid.UUID
    started_at: datetime
    last_message_at: datetime
    messages: list[StudentMessage]


class StudentConversationSummary(BaseModel):
    id: uuid.UUID
    started_at: datetime
    last_message_at: datetime
    preview: str | None = Field(description="Start of the first question.")
