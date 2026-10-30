import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Period = Literal["7d", "30d", "all"]


class InactiveReason(BaseModel):
    criterion: Literal["inactive"]
    days_inactive: int
    threshold_days: int
    since: datetime = Field(
        description="The last activity, or joining the course if there was none."
    )
    never_active: bool


class ErrorRateReason(BaseModel):
    criterion: Literal["error_rate"]
    mistakes: int
    assessed: int
    window_days: int
    min_exercises: int
    threshold_rate: float


RiskReason = Annotated[
    InactiveReason | ErrorRateReason, Field(discriminator="criterion")
]


class ActivityCounts(BaseModel):
    messages: int = Field(description="Messages students sent to the tutor.")
    exercises: int = Field(description="Exercises submitted, whatever the verdict.")


class TopicErrors(BaseModel):
    topic_id: uuid.UUID | None
    topic_name: str | None = Field(description="None for mistakes without a topic.")
    topic_deleted: bool
    errors: int
    students: int
    top_error_type: str


class StudentErrors(BaseModel):
    student_id: uuid.UUID
    display_name: str
    errors: int
    top_error_type: str
    top_topic_name: str | None


class AtRiskStudent(BaseModel):
    student_id: uuid.UUID
    display_name: str
    last_activity_at: datetime | None
    reasons: list[RiskReason]


class TeacherDashboard(BaseModel):
    period: Period
    since: datetime | None = Field(description="Start of the period; None for 'all'.")
    activity: ActivityCounts
    enough_data: bool = Field(
        description="At least `thresholds.messages` messages or `thresholds.exercises` "
        "exercises in the period."
    )
    thresholds: ActivityCounts
    errors_by_topic: list[TopicErrors]
    errors_by_student: list[StudentErrors]
    at_risk: list[AtRiskStudent] = Field(
        description="Independent of the period: each criterion has its own window."
    )
    criteria_provisional: bool


class WeekActivity(BaseModel):
    week_start: date = Field(description="Monday of the week (UTC).")
    messages: int
    exercises: int


class StudentRisk(BaseModel):
    student_id: uuid.UUID
    display_name: str
    at_risk: bool
    reasons: list[RiskReason]
    last_activity_at: datetime | None
    weekly_activity: list[WeekActivity] = Field(
        description="The last 8 weeks, oldest first."
    )
    criteria_provisional: bool


class RiskCriterionView(BaseModel):
    code: str
    enabled: bool
    thresholds: dict[str, float | int]


class RiskCriteriaList(BaseModel):
    provisional: bool = Field(
        description="True while the criteria are the technical team's draft (spec 004)."
    )
    items: list[RiskCriterionView]
