"""Adaptive quizzes over the teacher's approved questions (S6, specs/006).

Answering never calls the model. The level follows a provisional rule (FR-006): a quiz
starts at `quiz_start_level` and moves one level after `quiz_streak` right or wrong
answers in a row.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.models import Enrolment, Quiz, QuizItem, QuizQuestion, Topic
from app.schemas import quizzes as schemas
from app.services import consent, tutor

MIN_LEVEL, MAX_LEVEL = 1, 3


@dataclass(frozen=True)
class Adaptation:
    level: int
    streak: int


def run(streak: int, correct: bool) -> int:
    """The signed streak including this answer: > 0 right in a row, < 0 wrong."""
    if correct:
        return streak + 1 if streak > 0 else 1
    return streak - 1 if streak < 0 else -1


def adapt(level: int, streak: int, correct: bool, streak_needed: int) -> Adaptation:
    """The level and streak after an answer; the streak restarts on a level change."""
    streak = run(streak, correct)
    if streak >= streak_needed and level < MAX_LEVEL:
        return Adaptation(level + 1, 0)
    if -streak >= streak_needed and level > MIN_LEVEL:
        return Adaptation(level - 1, 0)
    return Adaptation(level, streak)


# --- Views -------------------------------------------------------------------------


def _current(quiz: Quiz) -> QuizItem | None:
    if quiz.status != "in_progress":
        return None
    return next((item for item in quiz.items if item.answered_at is None), None)


def _answered(quiz: Quiz) -> list[QuizItem]:
    return [item for item in quiz.items if item.answered_at is not None]


def _citations(item: QuizItem) -> list:
    question = item.question
    return [tutor.citation_view(c) for c in question.citations] if question else []


def _summary(quiz: Quiz) -> schemas.QuizSummary | None:
    if quiz.status != "completed":
        return None
    scores: dict[tuple[uuid.UUID | None, str], list[int]] = {}
    for item in _answered(quiz):
        score = scores.setdefault((item.topic_id, item.topic_name), [0, 0])
        score[0] += int(bool(item.correct))
        score[1] += 1
    return schemas.QuizSummary(
        score=sum(right for right, _ in scores.values()),
        total=sum(total for _, total in scores.values()),
        final_level=quiz.level,
        by_topic=[
            schemas.TopicScore(
                topic_id=topic_id, topic_name=name, correct=right, total=total
            )
            for (topic_id, name), (right, total) in scores.items()
        ],
    )


def quiz_view(quiz: Quiz) -> schemas.Quiz:
    current = _current(quiz)
    return schemas.Quiz(
        id=quiz.id,
        topic_id=quiz.topic_id,
        topic_name=quiz.topic_name,
        status=quiz.status,  # type: ignore[arg-type]
        question_count=quiz.question_count,
        answered_count=len(_answered(quiz)),
        level=quiz.level,
        current=schemas.QuizQuestion(
            id=current.question_id,
            position=current.position,
            statement=current.statement,
            options=list(current.options),
            difficulty=current.difficulty,
            topic_name=current.topic_name,
        )
        if current and current.question_id
        else None,
        summary=_summary(quiz),
        started_at=quiz.started_at,
        completed_at=quiz.completed_at,
    )


def quiz_detail(quiz: Quiz) -> schemas.QuizDetail:
    return schemas.QuizDetail(
        **quiz_view(quiz).model_dump(),
        items=[
            schemas.AnsweredItem(
                position=item.position,
                statement=item.statement,
                options=list(item.options),
                difficulty=item.difficulty,
                topic_name=item.topic_name,
                choice=item.choice,  # type: ignore[arg-type]
                correct=bool(item.correct),
                correct_option=item.correct_option,
                explanation=item.explanation,
                citations=_citations(item),
                answered_at=item.answered_at,  # type: ignore[arg-type]
            )
            for item in _answered(quiz)
        ],
    )


# --- Picking questions -------------------------------------------------------------


def _approved(course_id: uuid.UUID, topic_id: uuid.UUID | None):
    query = select(QuizQuestion).where(
        QuizQuestion.course_id == course_id, QuizQuestion.status == "approved"
    )
    return query.where(QuizQuestion.topic_id == topic_id) if topic_id else query


def _times_answered(
    session: Session, quiz: Quiz, ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    rows = session.execute(
        select(QuizItem.question_id, func.count())
        .join(Quiz, Quiz.id == QuizItem.quiz_id)
        .where(
            Quiz.student_id == quiz.student_id,
            Quiz.course_id == quiz.course_id,
            QuizItem.question_id.in_(ids),
            QuizItem.answered_at.is_not(None),
        )
        .group_by(QuizItem.question_id)
    ).all()
    return dict(rows)  # type: ignore[arg-type]


def _pick(session: Session, quiz: Quiz) -> QuizQuestion | None:
    """The nearest level first, then the questions answered least (AS4, AS6)."""
    used = {item.question_id for item in quiz.items}
    candidates = [
        q
        for q in session.scalars(_approved(quiz.course_id, quiz.topic_id))
        if q.id not in used
    ]
    if not candidates:
        return None
    answered = _times_answered(session, quiz, [q.id for q in candidates])
    return min(
        candidates,
        key=lambda q: (
            abs(q.difficulty - quiz.level),
            answered.get(q.id, 0),
            q.difficulty,
            q.created_at,
            q.id,
        ),
    )


def _add_item(session: Session, quiz: Quiz, question: QuizQuestion) -> None:
    session.add(
        QuizItem(
            quiz_id=quiz.id,
            question_id=question.id,
            position=len(quiz.items) + 1,
            topic_id=question.topic_id,
            topic_name=question.topic.name,
            statement=question.statement,
            options=list(question.options),
            correct_option=question.correct_option,
            explanation=question.explanation,
            difficulty=question.difficulty,
        )
    )
    session.flush()
    session.expire(quiz, ["items"])


def _complete(quiz: Quiz) -> None:
    quiz.status = "completed"
    quiz.completed_at = datetime.now(UTC)


# --- Flow --------------------------------------------------------------------------


def start(
    session: Session,
    settings: Settings,
    enrolment: Enrolment,
    topic_id: uuid.UUID | None,
) -> schemas.Quiz:
    consent.require(session, settings, enrolment.student_id)
    topic = session.get(Topic, topic_id) if topic_id else None
    if topic_id and (topic is None or topic.course_id != enrolment.course_id):
        raise not_found("Topic")
    available = (
        session.scalar(
            select(func.count()).select_from(
                _approved(enrolment.course_id, topic_id).subquery()
            )
        )
        or 0
    )
    if not available:
        raise ApiError(
            409, "no_questions", "The teacher has not published questions yet."
        )
    quiz = Quiz(
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        topic_id=topic.id if topic else None,
        topic_name=topic.name if topic else None,
        question_count=min(settings.quiz_length, available),
        level=min(max(settings.quiz_start_level, MIN_LEVEL), MAX_LEVEL),
        streak=0,
    )
    session.add(quiz)
    session.flush()
    question = _pick(session, quiz)
    assert question is not None  # there are approved questions
    _add_item(session, quiz, question)
    session.refresh(quiz)
    return quiz_view(quiz)


def get_quiz(session: Session, enrolment: Enrolment, quiz_id: uuid.UUID) -> Quiz:
    quiz = session.get(Quiz, quiz_id)
    if (
        quiz is None
        or quiz.course_id != enrolment.course_id
        or quiz.student_id != enrolment.student_id
    ):
        raise not_found("Quiz")
    return quiz


def list_quizzes(
    session: Session, enrolment: Enrolment, limit: int, offset: int
) -> tuple[list[schemas.Quiz], int]:
    query = select(Quiz).where(
        Quiz.course_id == enrolment.course_id,
        Quiz.student_id == enrolment.student_id,
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Quiz.started_at.desc(), Quiz.id).limit(limit).offset(offset)
    ).all()
    return [quiz_view(q) for q in rows], total


def answer(
    session: Session,
    settings: Settings,
    enrolment: Enrolment,
    quiz: Quiz,
    payload: schemas.QuizAnswer,
) -> schemas.AnswerResult:
    consent.require(session, settings, enrolment.student_id)
    if quiz.status == "completed":
        raise ApiError(409, "quiz_completed", "This quiz is already completed.")
    item = _current(quiz)
    if item is None or item.question_id != payload.question_id:
        raise ApiError(
            409, "not_current_question", "Answer the current question of the quiz."
        )
    item.choice = payload.choice
    item.correct = payload.choice == item.correct_option
    item.answered_at = datetime.now(UTC)

    before = quiz.level
    adaptation = adapt(quiz.level, quiz.streak, item.correct, settings.quiz_streak)
    change = (
        schemas.DifficultyChange(
            from_level=before,
            to_level=adaptation.level,
            reason="correct_streak" if item.correct else "wrong_streak",
            streak=abs(run(quiz.streak, item.correct)),
        )
        if adaptation.level != before
        else None
    )
    quiz.level, quiz.streak = adaptation.level, adaptation.streak
    session.flush()

    if item.position >= quiz.question_count:
        _complete(quiz)
    else:
        question = _pick(session, quiz)
        if question is None:
            # Questions were rejected meanwhile: the quiz ends with what was answered.
            quiz.question_count = item.position
            _complete(quiz)
        else:
            _add_item(session, quiz, question)
    session.flush()
    session.refresh(quiz)
    return schemas.AnswerResult(
        correct=item.correct,
        correct_option=item.correct_option,
        explanation=item.explanation,
        citations=_citations(item),
        difficulty_change=change,
        quiz=quiz_view(quiz),
    )
