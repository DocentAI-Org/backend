import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.chat import Citation, Correction

Verdict = Literal["correct", "partially_correct", "incorrect"]


class SubmissionCreate(BaseModel):
    problem_statement: str = Field(min_length=1, max_length=2000)
    worked_answer: str = Field(min_length=1, max_length=4000)


class StudentSubmission(BaseModel):
    id: uuid.UUID
    problem_statement: str
    worked_answer: str
    verdict: Verdict
    mistake_location: str | None
    error_type: str | None
    topic_name: str | None
    explanation: str
    explanation_kind: Literal["answer", "no_source"]
    citations: list[Citation]
    saved_to_record: bool
    is_stub: bool = Field(description="True while feedback is a fixed placeholder.")
    correction: Correction | None
    created_at: datetime


class LearningRecordEntry(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    error_type: str
    topic_id: uuid.UUID | None
    topic_name: str | None
    topic_deleted: bool
    created_at: datetime
