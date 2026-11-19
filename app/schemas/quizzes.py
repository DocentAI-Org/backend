import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from app.core.types import ExplanationKind, QuestionOrigin, QuestionStatus, QuizStatus
from app.schemas.chat import Citation
from app.schemas.common import CleanText

Level = Annotated[
    int, Field(ge=1, le=3, description="1 basic, 2 intermediate, 3 advanced.")
]
Choice = Annotated[int, Field(ge=0, le=3, description="Index of the option, 0-3.")]


def _four_distinct(options: list[str]) -> list[str]:
    cleaned = [option.strip() for option in options]
    if any(not option for option in cleaned):
        raise ValueError("Options cannot be empty.")
    if len({option.casefold() for option in cleaned}) != len(cleaned):
        raise ValueError("Options must be different.")
    return cleaned


Options = Annotated[
    list[Annotated[CleanText, Field(max_length=300)]],
    Field(min_length=4, max_length=4),
    AfterValidator(_four_distinct),
]


# --- Teacher -----------------------------------------------------------------------


class GenerateQuestions(BaseModel):
    count: int = Field(default=5, ge=1, le=10)


class TeacherQuestion(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    topic_name: str
    statement: str
    options: list[str]
    correct_option: int
    explanation: str
    difficulty: int
    status: QuestionStatus
    origin: QuestionOrigin = Field(
        description="`edited` once the teacher changes an AI draft."
    )
    citations: list[Citation]
    answered_count: int = Field(description="Answers given in students' quizzes.")
    correct_rate: float | None = Field(
        description="Share of those answers that were right; null before any."
    )
    reviewed_at: datetime | None
    created_at: datetime


class GeneratedQuestions(BaseModel):
    kind: ExplanationKind = Field(
        description="`no_source` when the material gave no usable question."
    )
    questions: list[TeacherQuestion]


class QuestionCounts(BaseModel):
    pending: int
    approved: int
    rejected: int


class QuestionPage(BaseModel):
    items: list[TeacherQuestion]
    total: int
    limit: int
    offset: int
    counts: QuestionCounts = Field(
        description="Questions per status, for the topic filter if given."
    )


class QuestionUpdate(BaseModel):
    statement: CleanText | None = Field(default=None, min_length=1, max_length=1000)
    options: Options | None = None
    correct_option: Choice | None = None
    explanation: CleanText | None = Field(default=None, min_length=1, max_length=1000)
    difficulty: Level | None = None
    status: QuestionStatus | None = None


# --- Student -----------------------------------------------------------------------


class QuizStart(BaseModel):
    topic_id: uuid.UUID | None = Field(
        default=None, description="Omit for a quiz over every topic."
    )


class QuizQuestion(BaseModel):
    id: uuid.UUID = Field(description="The question to send back with the answer.")
    position: int
    statement: str
    options: list[str]
    difficulty: int
    topic_name: str


class AnsweredItem(BaseModel):
    position: int
    statement: str
    options: list[str]
    difficulty: int
    topic_name: str
    choice: int
    correct: bool
    correct_option: int
    explanation: str
    citations: list[Citation]
    answered_at: datetime


class TopicScore(BaseModel):
    topic_id: uuid.UUID | None
    topic_name: str
    correct: int
    total: int


class QuizSummary(BaseModel):
    score: int
    total: int
    final_level: int
    by_topic: list[TopicScore]


class StartBasis(BaseModel):
    """Why a quiz started at its level (specs/021), as it was then."""

    reason: Literal["mastery", "no_score", "fixed"] = Field(
        description="`no_score`: too few items for a mastery level; `fixed`: the "
        "course starts every quiz at `start_level`."
    )
    mastery_level: Literal["starting", "progressing", "mastered"] | None = Field(
        description="The topic's level, or for a quiz on every topic the level of the "
        "mean score of the scored topics."
    )
    score: float | None


class Quiz(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID | None
    topic_name: str | None
    status: QuizStatus
    question_count: int
    answered_count: int
    level: int = Field(description="Current difficulty level, 1-3.")
    start_basis: StartBasis | None = Field(
        description="Why it started at its level; null for quizzes before specs/021."
    )
    current: QuizQuestion | None = Field(description="Null once completed.")
    summary: QuizSummary | None = Field(description="Set once completed.")
    started_at: datetime
    completed_at: datetime | None


class QuizDetail(Quiz):
    items: list[AnsweredItem] = Field(description="The answered questions, in order.")


class QuizTopic(BaseModel):
    topic_id: uuid.UUID
    topic_name: str
    question_count: int = Field(description="Approved questions in the topic.")


class QuizAnswer(BaseModel):
    question_id: uuid.UUID
    choice: Choice


class DifficultyChange(BaseModel):
    from_level: int
    to_level: int
    reason: Literal["correct_streak", "wrong_streak", "level_exhausted"] = Field(
        description="`level_exhausted`: no question left at the previous level."
    )
    streak: int = Field(
        description="Right (or wrong) answers in a row, this one included."
    )


class AnswerResult(BaseModel):
    correct: bool
    correct_option: int
    explanation: str
    citations: list[Citation]
    difficulty_change: DifficultyChange | None = Field(
        description="Set when this answer moved the level (provisional rule, spec 006)."
    )
    quiz: Quiz
