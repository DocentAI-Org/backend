import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.chat import Adaptation, Citation, Correction
from app.schemas.common import CleanText

Verdict = Literal["correct", "partially_correct", "incorrect", "not_assessed"]


class SubmissionCreate(BaseModel):
    problem_statement: CleanText = Field(min_length=1, max_length=2000)
    worked_answer: CleanText = Field(min_length=1, max_length=4000)


class RepeatedMistake(BaseModel):
    count: int = Field(
        description="Mistakes of this type and topic in the window, up to this one."
    )
    window_days: int
    error_type: str
    topic_name: str | None


class OvercomePattern(BaseModel):
    """A repeated pattern this correct exercise completes (specs/022, provisional)."""

    error_type: str
    topic_name: str | None
    count: int = Field(description="Its mistakes in the window, up to the latest.")
    correct: int = Field(description="Correct exercises in a row in the topic since.")


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
    is_stub: bool = Field(
        description="Always false since real feedback (specs/003); to be removed."
    )
    correction: Correction | None
    repeated_mistake: RepeatedMistake | None = Field(
        description="Set when this mistake repeats a pattern (specs/005, provisional)."
    )
    adaptation: Adaptation | None = Field(
        default=None, description="Set when the feedback was adapted (specs/013)."
    )
    overcome: list[OvercomePattern] = Field(
        default_factory=list,
        description="Repeated patterns this correct exercise overcomes (specs/022); "
        "said once, on the exercise that completes the run.",
    )
    created_at: datetime


class MistakeReview(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    error_type: str
    topic_name: str | None
    kind: Literal["answer", "no_source"]
    explanation: str
    worked_example: str | None
    practice: list[str] = Field(description="Practice statements, without solutions.")
    citations: list[Citation]
    created_at: datetime


class LearningRecordEntry(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    error_type: str
    topic_id: uuid.UUID | None
    topic_name: str | None
    topic_deleted: bool
    created_at: datetime


class Localized(BaseModel):
    es: str
    en: str


class ErrorTypeView(BaseModel):
    code: str = Field(description="Stable identifier stored in the learning record.")
    label: Localized
    description: Localized


class ErrorTaxonomy(BaseModel):
    provisional: bool = Field(
        description="True while the taxonomy is the technical team's draft (specs/003)."
    )
    items: list[ErrorTypeView]
