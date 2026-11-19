import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.types import Phase


class TestStep(BaseModel):
    kind: Literal["test"]
    phase: Phase


class ResumeQuizStep(BaseModel):
    kind: Literal["resume_quiz"]
    quiz_id: uuid.UUID
    topic_name: str | None = Field(description="Null for a quiz on every topic.")
    answered: int
    total: int


class ReviewMistakeStep(BaseModel):
    kind: Literal["review_mistake"]
    error_type: str
    topic_id: uuid.UUID | None
    topic_name: str | None
    count: int
    window_days: int
    submission_id: uuid.UUID = Field(description="The pattern's latest submission.")
    reviewed: bool = Field(description="Its targeted review was already requested.")


class PracticeTopicStep(BaseModel):
    kind: Literal["practice_topic"]
    topic_id: uuid.UUID
    topic_name: str
    level: Literal["starting", "progressing"]
    score: float = Field(description="Share right, 0-1 (spec 007).")
    items: int = Field(description="Graded items behind the score.")
    has_questions: bool = Field(description="The topic has approved quiz questions.")


class StartTopicStep(BaseModel):
    kind: Literal["start_topic"]
    topic_id: uuid.UUID
    topic_name: str
    level: Literal["not_started", "insufficient"]
    items: int
    min_items: int = Field(description="Items needed for a score.")
    has_questions: bool


NextStep = Annotated[
    TestStep | ResumeQuizStep | ReviewMistakeStep | PracticeTopicStep | StartTopicStep,
    Field(discriminator="kind"),
]


class NextSteps(BaseModel):
    provisional: bool = Field(
        description="True while the criteria are the technical team's draft (spec 015)."
    )
    steps: list[NextStep] = Field(description="At most three, most important first.")
