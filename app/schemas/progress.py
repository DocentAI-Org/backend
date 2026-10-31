import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["not_started", "insufficient", "starting", "progressing", "mastered"]


class ProgressCriteria(BaseModel):
    window: int = Field(description="Latest graded items that count, per topic.")
    min_items: int = Field(description="Items needed for a score.")
    progressing: float = Field(
        description="Score from which the level is `progressing`."
    )
    mastered: float = Field(description="Score from which the level is `mastered`.")


class ProgressBasis(BaseModel):
    """The items behind the score: those in the window."""

    exercises_correct: int
    exercises_partial: int
    exercises_total: int
    quiz_right: int
    quiz_total: int


class WeekScore(BaseModel):
    week_start: date = Field(description="Monday of the week (UTC).")
    score: float | None = Field(description="Null with too few items by then.")


class TopicError(BaseModel):
    error_type: str
    count: int
    latest_submission_id: uuid.UUID


class TopicProgress(BaseModel):
    topic_id: uuid.UUID | None = Field(
        description="Null for graded work without a topic."
    )
    topic_name: str | None
    level: Level
    score: float | None = Field(description="Share right, 0-1; null below `min_items`.")
    basis: ProgressBasis
    history: list[WeekScore] = Field(description="The last 8 weeks, oldest first.")
    top_errors: list[TopicError] = Field(
        description="Up to three most frequent error types (exercises only)."
    )
    last_activity_at: datetime | None


class Progress(BaseModel):
    provisional: bool = Field(
        description="True while the criteria are the technical team's draft (spec 007)."
    )
    criteria: ProgressCriteria
    updated_at: datetime | None = Field(description="Latest graded activity.")
    quizzes_completed: int
    topics: list[TopicProgress] = Field(description="Every course topic, in order.")
    unassigned: TopicProgress | None = Field(
        description="Graded work without a topic; null if there is none."
    )
