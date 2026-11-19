"""Recommended next steps in a course (specs/020, provisional), computed on read from
the tests, quizzes, repeated mistakes and mastery the platform already has."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    Enrolment,
    LearningRecordEntry,
    MistakeReview,
    Quiz,
    QuizQuestion,
)
from app.schemas import next_steps as schemas
from app.schemas.progress import TopicProgress
from app.services import course_tests, overcome, pedagogy, progress, quizzes

LIMIT = 3


def _tests(session: Session, enrolment: Enrolment) -> list[schemas.TestStep]:
    return [
        schemas.TestStep(kind="test", phase=phase.phase)
        for phase in course_tests.student_phases(session, enrolment)
        if phase.status == "open" and not phase.done and phase.question_count
    ]


def _resume_quiz(
    session: Session, enrolment: Enrolment
) -> schemas.ResumeQuizStep | None:
    quiz = session.scalar(
        select(Quiz)
        .where(
            Quiz.course_id == enrolment.course_id,
            Quiz.student_id == enrolment.student_id,
            Quiz.status == "in_progress",
        )
        .order_by(Quiz.started_at.desc(), Quiz.id)
        .limit(1)
    )
    if quiz is None:
        return None
    view = quizzes.quiz_view(quiz)
    if view.current is None:
        return None
    return schemas.ResumeQuizStep(
        kind="resume_quiz",
        quiz_id=quiz.id,
        topic_name=quiz.topic_name,
        answered=view.answered_count,
        total=view.question_count,
    )


def _review_mistake(
    session: Session, enrolment: Enrolment
) -> schemas.ReviewMistakeStep | None:
    """The most repeated pattern (error type and topic) in the window (spec 005) that is
    not overcome yet (spec 022)."""
    threshold = pedagogy.in_effect(
        session, enrolment.course_id
    ).criteria.repeated_mistakes
    since = datetime.now(UTC) - timedelta(days=threshold.window_days)
    count = func.count(LearningRecordEntry.id)
    latest = func.max(LearningRecordEntry.created_at)
    rows = session.execute(
        select(
            LearningRecordEntry.error_type,
            LearningRecordEntry.topic_id,
            LearningRecordEntry.topic_name,
            count,
            latest,
        )
        .where(
            LearningRecordEntry.course_id == enrolment.course_id,
            LearningRecordEntry.student_id == enrolment.student_id,
            LearningRecordEntry.created_at >= since,
        )
        .group_by(
            LearningRecordEntry.error_type,
            LearningRecordEntry.topic_id,
            LearningRecordEntry.topic_name,
        )
        .having(count >= threshold.count)
        .order_by(count.desc(), latest.desc())
    ).all()
    # Patterns already overcome are not recommended (specs/022).
    row = next(
        (
            r
            for r in rows
            if overcome.correct_run(
                session, enrolment.course_id, enrolment.student_id, r[1], r[2], r[4]
            )
            < threshold.overcome_after
        ),
        None,
    )
    if row is None:
        return None
    error_type, topic_id, topic_name, times, _ = row
    same_topic = (
        LearningRecordEntry.topic_id == topic_id
        if topic_id is not None
        else LearningRecordEntry.topic_id.is_(None)
        & LearningRecordEntry.topic_name.is_not_distinct_from(topic_name)
    )
    submission_id = session.scalar(
        select(LearningRecordEntry.submission_id)
        .where(
            LearningRecordEntry.course_id == enrolment.course_id,
            LearningRecordEntry.student_id == enrolment.student_id,
            LearningRecordEntry.error_type == error_type,
            same_topic,
        )
        .order_by(LearningRecordEntry.created_at.desc())
        .limit(1)
    )
    assert submission_id is not None  # the pattern exists, so an entry does too
    reviewed = session.scalar(
        select(exists().where(MistakeReview.submission_id == submission_id))
    )
    return schemas.ReviewMistakeStep(
        kind="review_mistake",
        error_type=error_type,
        topic_id=topic_id,
        topic_name=topic_name,
        count=times,
        window_days=threshold.window_days,
        submission_id=submission_id,
        reviewed=bool(reviewed),
    )


def _with_questions(session: Session, course_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        session.scalars(
            select(QuizQuestion.topic_id)
            .where(
                QuizQuestion.course_id == course_id,
                QuizQuestion.status == "approved",
            )
            .distinct()
        )
    )


def _items(topic: TopicProgress) -> int:
    return topic.basis.exercises_total + topic.basis.quiz_total


def _topic_steps(
    session: Session, settings: Settings, enrolment: Enrolment
) -> tuple[schemas.PracticeTopicStep | None, schemas.StartTopicStep | None]:
    current = progress.student_progress(
        session, settings, enrolment.course_id, enrolment.student_id
    )
    asked = _with_questions(session, enrolment.course_id)
    weak = [t for t in current.topics if t.level in ("starting", "progressing")]
    # min() keeps the first of equal scores: course order.
    weakest = min(weak, key=lambda t: t.score or 0.0, default=None)
    fresh = next(
        (t for t in current.topics if t.level in ("not_started", "insufficient")),
        None,
    )
    practice = (
        schemas.PracticeTopicStep(
            kind="practice_topic",
            topic_id=weakest.topic_id,  # type: ignore[arg-type]
            topic_name=weakest.topic_name,  # type: ignore[arg-type]
            level=weakest.level,  # type: ignore[arg-type]
            score=weakest.score or 0.0,
            items=_items(weakest),
            has_questions=weakest.topic_id in asked,
        )
        if weakest
        else None
    )
    start = (
        schemas.StartTopicStep(
            kind="start_topic",
            topic_id=fresh.topic_id,  # type: ignore[arg-type]
            topic_name=fresh.topic_name,  # type: ignore[arg-type]
            level=fresh.level,  # type: ignore[arg-type]
            items=_items(fresh),
            min_items=current.criteria.min_items,
            has_questions=fresh.topic_id in asked,
        )
        if fresh
        else None
    )
    return practice, start


def next_steps(
    session: Session, settings: Settings, enrolment: Enrolment
) -> schemas.NextSteps:
    """The same for the student and the teacher (AGENTS.md I)."""
    practice, start = _topic_steps(session, settings, enrolment)
    candidates = [
        *_tests(session, enrolment),
        _resume_quiz(session, enrolment),
        _review_mistake(session, enrolment),
        practice,
        start,
    ]
    return schemas.NextSteps(
        provisional=pedagogy.in_effect(session, enrolment.course_id).provisional,
        steps=[step for step in candidates if step is not None][:LIMIT],
    )
