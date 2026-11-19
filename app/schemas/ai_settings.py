"""AI settings (specs/019): the server's values (env), the study's and each course's,
per group; models are chosen per task."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.config import Effort, Provider, Task
from app.core.types import Period

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
    credential_id: uuid.UUID | None = Field(
        default=None, description="A stored key; null: the server's key."
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


Instruction = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class Instructions(BaseModel):
    """The teacher's words for each task, after the rules; null or empty: none."""

    tutor: Instruction | None = None
    feedback: Instruction | None = None
    review: Instruction | None = None
    questions: Instruction | None = None


class Ceiling(BaseModel):
    """Messages per student and day across all courses; null is no ceiling."""

    messages: int | None = Field(ge=1, le=10000)


class Values(BaseModel):
    models: dict[Task, ResolvedModel]
    limits: Limits
    retrieval: Retrieval
    instructions: Instructions


class StudyValues(Values):
    ceiling: Ceiling


class StudyOverrides(BaseModel):
    models: TaskModels = TaskModels()
    limits: Limits | None = None
    retrieval: Retrieval | None = None
    instructions: Instructions | None = None
    ceiling: Ceiling | None = None
    allow_teacher_keys: bool = Field(
        default=False, description="Teachers may add their own keys to their courses."
    )


class CourseOverrides(BaseModel):
    models: TaskModels = TaskModels()
    limits: Limits | None = None
    retrieval: Retrieval | None = None
    instructions: Instructions | None = None


class Notice(BaseModel):
    """A task that went back to the inherited model, and why."""

    task: Task
    model: str
    reason: Literal["credential_removed", "model_withdrawn", "teacher_keys_disabled"]
    at: datetime


class StudyAISettings(BaseModel):
    server: StudyValues = Field(description="The values in the server's environment.")
    study: StudyOverrides = Field(description="What the study changes; null inherits.")
    effective: StudyValues
    notices: list[Notice] = Field(description="Cleared when the settings are saved.")
    updated_at: datetime


class CourseAISettings(BaseModel):
    inherited: Values = Field(description="What applies without the course's values.")
    course: CourseOverrides = Field(description="What the course changes.")
    effective: Values
    ceiling: Ceiling = Field(description="The study's daily ceiling, for reference.")
    allow_teacher_keys: bool
    notices: list[Notice] = Field(description="Cleared when the settings are saved.")


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
    credential_id: uuid.UUID | None = Field(
        default=None, description="Null for the server's own keys."
    )
    scope: Literal["server", "study", "course"] = "server"


class AIModels(BaseModel):
    sources: list[ModelSource]


class AITestRequest(BaseModel):
    """A message to try the settings with; `settings` are the unsaved ones (null:
    the saved ones)."""

    task: Literal["tutor", "feedback"]
    settings: CourseOverrides | None = None
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    problem_statement: str | None = Field(default=None, min_length=1, max_length=2000)
    worked_answer: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def fields_of_the_task(self) -> "AITestRequest":
        if self.task == "tutor" and not self.message:
            raise ValueError("The tutor test needs a message.")
        if self.task == "feedback" and not (
            self.problem_statement and self.worked_answer
        ):
            raise ValueError("The feedback test needs a problem and an answer.")
        return self


class AITestResult(BaseModel):
    kind: str = Field(description="The reply kind, or the verdict for feedback.")
    text: str
    model: str | None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    fragments: int = Field(description="Fragments of material sent to the model.")


class TaskUsage(BaseModel):
    task: Task
    messages: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class UsageWindow(BaseModel):
    days: int
    tasks: list[TaskUsage]


class StudentUsage(BaseModel):
    student_id: uuid.UUID
    display_name: str
    used: int


class AIUsage(BaseModel):
    windows: list[UsageWindow] = Field(description="The last 7 and 30 days.")
    limit: int | None = Field(description="The course's limit in effect; null: none.")
    period: Period
    top_students: list[StudentUsage] = Field(
        description="Those who used most in the current period (at most 5)."
    )
