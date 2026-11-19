import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.types import Phase, PhaseStatus
from app.schemas.common import CleanText
from app.schemas.quizzes import Choice, Options

# --- Teacher -----------------------------------------------------------------------


class TestQuestionCreate(BaseModel):
    topic_id: uuid.UUID
    statement: CleanText = Field(min_length=1, max_length=1000)
    options: Options
    correct_option: Choice


class TestQuestionUpdate(BaseModel):
    topic_id: uuid.UUID | None = None
    statement: CleanText | None = Field(default=None, min_length=1, max_length=1000)
    options: Options | None = None
    correct_option: Choice | None = None


class CopyQuizQuestion(BaseModel):
    question_id: uuid.UUID = Field(
        description="An approved quiz question of the course."
    )


class TestQuestion(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID | None
    topic_name: str
    position: int
    statement: str
    options: list[str]
    correct_option: int


class TestPhaseView(BaseModel):
    phase: Phase
    status: PhaseStatus
    opened_at: datetime | None
    closed_at: datetime | None
    submitted_count: int


class PhaseUpdate(BaseModel):
    status: Literal["open", "closed"]


class CourseTest(BaseModel):
    locked: bool = Field(
        description="True once the pre-test has been opened: questions are frozen."
    )
    questions: list[TestQuestion]
    phases: list[TestPhaseView]


class TestTopicScore(BaseModel):
    topic_id: uuid.UUID | None
    topic_name: str
    right: int
    total: int


class PhaseScore(BaseModel):
    submitted_at: datetime
    right: int
    total: int
    by_topic: list[TestTopicScore]


class StudentResult(BaseModel):
    student_id: uuid.UUID
    display_name: str
    pre: PhaseScore | None
    post: PhaseScore | None


class TopicAverage(BaseModel):
    topic_id: uuid.UUID | None
    topic_name: str
    score: float = Field(description="Mean share right, 0-1.")


class PhaseAverage(BaseModel):
    phase: Phase
    submitted: int
    score: float | None = Field(description="Mean share right, 0-1; null if none.")
    by_topic: list[TopicAverage]


class TestResults(BaseModel):
    question_count: int
    phases: list[TestPhaseView]
    students: list[StudentResult] = Field(description="Active students of the course.")
    averages: list[PhaseAverage]


# --- Student -----------------------------------------------------------------------


class StudentTestPhase(BaseModel):
    phase: Phase
    status: PhaseStatus
    done: bool
    question_count: int


class StudentTestQuestion(BaseModel):
    id: uuid.UUID
    position: int
    statement: str
    options: list[str]
    topic_name: str


class StudentTest(BaseModel):
    phase: Phase
    status: PhaseStatus
    done: bool
    submitted_at: datetime | None
    questions: list[StudentTestQuestion] = Field(
        description="Empty once done; never with the right option."
    )


class TestAnswerIn(BaseModel):
    question_id: uuid.UUID
    choice: Choice


class TestSubmission(BaseModel):
    answers: list[TestAnswerIn] = Field(description="One answer per question.")


class TestSubmitted(BaseModel):
    phase: Phase
    submitted_at: datetime
