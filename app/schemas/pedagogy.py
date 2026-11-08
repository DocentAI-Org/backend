"""Pedagogical criteria (specs/015): study defaults and course overrides, per group."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Group = Literal[
    "inactive", "error_rate", "repeated_mistakes", "adaptation", "mastery", "quiz"
]
GROUPS: tuple[Group, ...] = (
    "inactive",
    "error_rate",
    "repeated_mistakes",
    "adaptation",
    "mastery",
    "quiz",
)


class InactiveCriteria(BaseModel):
    """At risk after this many days without activity (spec 004)."""

    enabled: bool
    days: int = Field(ge=1, le=365)


class ErrorRateCriteria(BaseModel):
    """At risk with this share of mistakes in enough assessed exercises (spec 004)."""

    enabled: bool
    rate: float = Field(gt=0, le=1)
    min_exercises: int = Field(ge=1, le=100)
    window_days: int = Field(ge=1, le=365)


class RepeatedMistakeCriteria(BaseModel):
    """The same mistake this many times in this many days (spec 005)."""

    count: int = Field(ge=1, le=50)
    window_days: int = Field(ge=1, le=365)


class AdaptationCriteria(BaseModel):
    """Explanations adapted to repeated mistakes (spec 013)."""

    enabled: bool


class MasteryCriteria(BaseModel):
    """Latest items that count, items needed for a level, and the scores (spec 007)."""

    window: int = Field(ge=1, le=100)
    min_items: int = Field(ge=1, le=100)
    progressing: float = Field(gt=0, le=1)
    mastered: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def consistent(self) -> "MasteryCriteria":
        if self.min_items > self.window:
            raise ValueError("min_items cannot be more than window.")
        if self.progressing >= self.mastered:
            raise ValueError("progressing must be below mastered.")
        return self


class QuizCriteria(BaseModel):
    """Quiz length, the streak that moves the level and the start (specs/006, 021)."""

    length: int = Field(ge=1, le=30)
    streak: int = Field(ge=1, le=10)
    start_level: int = Field(
        ge=1, le=3, description="The start without a score, or without `adaptive`."
    )
    adaptive: bool = Field(
        description="Start from the student's mastery and favour their weak topics."
    )


class Criteria(BaseModel):
    inactive: InactiveCriteria
    error_rate: ErrorRateCriteria
    repeated_mistakes: RepeatedMistakeCriteria
    adaptation: AdaptationCriteria
    mastery: MasteryCriteria
    quiz: QuizCriteria


class StudyCriteria(BaseModel):
    criteria: Criteria
    provisional: bool = Field(
        description="True until the educational stream agrees the defaults."
    )
    updated_at: datetime


class StudyCriteriaUpdate(BaseModel):
    criteria: Criteria
    provisional: bool


class CourseCriteriaUpdate(BaseModel):
    """A group's own values for the course, or null for the study's."""

    inactive: InactiveCriteria | None = None
    error_rate: ErrorRateCriteria | None = None
    repeated_mistakes: RepeatedMistakeCriteria | None = None
    adaptation: AdaptationCriteria | None = None
    mastery: MasteryCriteria | None = None
    quiz: QuizCriteria | None = None


class CourseCriteria(BaseModel):
    study: Criteria
    provisional: bool
    custom: dict[Group, bool] = Field(description="Groups the course overrides.")
    effective: Criteria
