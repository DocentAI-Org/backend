import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MessageKind = Literal["question", "answer", "hint", "no_source"]


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
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


class Allowance(BaseModel):
    limit: int
    used: int
    remaining: int
    resets_at: datetime


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
