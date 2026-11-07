"""AI settings (specs/019): the server's values (env), the study's and each course's,
per group; models are chosen per task."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import Effort, Provider, Task

Period = Literal["day", "week", "course"]
CountedTask = Literal["tutor", "feedback", "review"]
COUNTED_TASKS: tuple[CountedTask, ...] = ("tutor", "feedback", "review")
Origin = Literal["course", "study", "server"]


class ModelChoice(BaseModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=200)
    temperature: float | None = Field(
        default=None,
        ge=0,
        le=2,
        description="Null: the task's own (not for Anthropic).",
    )
    effort: Effort | None = None
    max_tokens: int | None = Field(
        default=None, ge=64, le=32000, description="Longest reply; null: the server's."
    )


class TaskModels(BaseModel):
    """A task's own model, or null for the one it inherits."""

    tutor: ModelChoice | None = None
    feedback: ModelChoice | None = None
    review: ModelChoice | None = None
    questions: ModelChoice | None = None


class ResolvedModel(ModelChoice):
    origin: Origin


class Limits(BaseModel):
    """Messages per student in the course and period; null is no limit."""

    messages: int | None = Field(ge=1, le=10000)
    period: Period
    counted_tasks: list[CountedTask] = Field(
        description="Student tasks that use messages."
    )

    @field_validator("counted_tasks")
    @classmethod
    def unique(cls, value: list[CountedTask]) -> list[CountedTask]:
        return [task for task in COUNTED_TASKS if task in value]


class Retrieval(BaseModel):
    top_k: int = Field(ge=1, le=10, description="Fragments sent to the model.")
    min_similarity: float = Field(ge=0, le=1)
    min_similarity_exercises: float = Field(ge=0, le=1)
    history_messages: int = Field(ge=0, le=20, description="Earlier messages kept.")


class Ceiling(BaseModel):
    """Messages per student and day across all courses; null is no ceiling."""

    messages: int | None = Field(ge=1, le=10000)


class Values(BaseModel):
    models: dict[Task, ResolvedModel]
    limits: Limits
    retrieval: Retrieval


class StudyValues(Values):
    ceiling: Ceiling


class StudyOverrides(BaseModel):
    models: TaskModels = TaskModels()
    limits: Limits | None = None
    retrieval: Retrieval | None = None
    ceiling: Ceiling | None = None


class CourseOverrides(BaseModel):
    models: TaskModels = TaskModels()
    limits: Limits | None = None
    retrieval: Retrieval | None = None


class StudyAISettings(BaseModel):
    server: StudyValues = Field(description="The values in the server's environment.")
    study: StudyOverrides = Field(description="What the study changes; null inherits.")
    effective: StudyValues
    updated_at: datetime


class CourseAISettings(BaseModel):
    inherited: Values = Field(description="What applies without the course's values.")
    course: CourseOverrides = Field(description="What the course changes.")
    effective: Values
    ceiling: Ceiling = Field(description="The study's daily ceiling, for reference.")


class ModelInfo(BaseModel):
    id: str
    label: str | None = None
    size_bytes: int | None = None
    parameter_size: str | None = None
    family: str | None = None


class ModelSource(BaseModel):
    provider: Provider
    label: str
    reachable: bool
    models: list[ModelInfo]


class AIModels(BaseModel):
    sources: list[ModelSource]
