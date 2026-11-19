"""Repeated mistakes overcome (specs/022, provisional): a mistake of a type in a topic
is overcome once the student's next `overcome_after` assessed exercises in that topic
are all correct; any other result in the topic restarts the count."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import ExerciseSubmission, LearningRecordEntry
from app.schemas.exercises import OvercomePattern
from app.services import pedagogy

ASSESSED = ("correct", "partially_correct", "incorrect")


def _same_topic(column_id, column_name, topic_id, topic_name):
    if topic_id is not None:
        return column_id == topic_id
    return column_id.is_(None) & column_name.is_not_distinct_from(topic_name)


def patterns_in_window(
    course_id: uuid.UUID, student_id: uuid.UUID, window_days: int
) -> Select:
    """The student's mistakes in the last `window_days`, one row per pattern (error
    type and topic): error_type, topic_id, topic_name, count and latest entry."""
    since = datetime.now(UTC) - timedelta(days=window_days)
    return (
        select(
            LearningRecordEntry.error_type,
            LearningRecordEntry.topic_id,
            LearningRecordEntry.topic_name,
            func.count(LearningRecordEntry.id),
            func.max(LearningRecordEntry.created_at),
        )
        .where(
            LearningRecordEntry.course_id == course_id,
            LearningRecordEntry.student_id == student_id,
            LearningRecordEntry.created_at >= since,
        )
        .group_by(
            LearningRecordEntry.error_type,
            LearningRecordEntry.topic_id,
            LearningRecordEntry.topic_name,
        )
    )


def correct_run(
    session: Session,
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    topic_id: uuid.UUID | None,
    topic_name: str | None,
    after: datetime,
    until: datetime | None = None,
) -> int:
    """Correct exercises in a row in the topic, counted back from the latest, after
    `after` (and up to `until`, included)."""
    query = (
        select(ExerciseSubmission.verdict)
        .where(
            ExerciseSubmission.course_id == course_id,
            ExerciseSubmission.student_id == student_id,
            ExerciseSubmission.verdict.in_(ASSESSED),
            ExerciseSubmission.is_stub.is_(False),
            ExerciseSubmission.created_at > after,
            _same_topic(
                ExerciseSubmission.topic_id,
                ExerciseSubmission.topic_name,
                topic_id,
                topic_name,
            ),
        )
        .order_by(ExerciseSubmission.created_at.desc())
    )
    if until is not None:
        query = query.where(ExerciseSubmission.created_at <= until)
    run = 0
    for verdict in session.scalars(query):
        if verdict != "correct":
            break
        run += 1
    return run


def run_since(verdicts_after: list[float]) -> int:
    """The same count over graded values in time order (1.0 is correct)."""
    run = 0
    for value in reversed(verdicts_after):
        if value != 1.0:
            break
        run += 1
    return run


def _repeated_before(
    session: Session,
    entry_filter,
    latest: datetime,
    window_days: int,
) -> int:
    return (
        session.scalar(
            select(func.count(LearningRecordEntry.id)).where(
                *entry_filter,
                LearningRecordEntry.created_at <= latest,
                LearningRecordEntry.created_at > latest - timedelta(days=window_days),
            )
        )
        or 0
    )


def overcome_by(
    session: Session, submission: ExerciseSubmission
) -> list[OvercomePattern]:
    """The repeated patterns (spec 005) this correct exercise completes: said once, when
    the run after the pattern's latest mistake reaches `overcome_after`."""
    if submission.verdict != "correct" or submission.is_stub:
        return []
    threshold = pedagogy.in_effect(
        session, submission.course_id
    ).criteria.repeated_mistakes
    same_topic = _same_topic(
        LearningRecordEntry.topic_id,
        LearningRecordEntry.topic_name,
        submission.topic_id,
        submission.topic_name,
    )
    base = (
        LearningRecordEntry.course_id == submission.course_id,
        LearningRecordEntry.student_id == submission.student_id,
        same_topic,
    )
    rows = session.execute(
        select(LearningRecordEntry.error_type, func.max(LearningRecordEntry.created_at))
        .where(*base, LearningRecordEntry.created_at < submission.created_at)
        .group_by(LearningRecordEntry.error_type)
        .order_by(LearningRecordEntry.error_type)
    ).all()
    found = []
    for error_type, latest in rows:
        run = correct_run(
            session,
            submission.course_id,
            submission.student_id,
            submission.topic_id,
            submission.topic_name,
            after=latest,
            until=submission.created_at,
        )
        if run != threshold.overcome_after:
            continue
        count = _repeated_before(
            session,
            (*base, LearningRecordEntry.error_type == error_type),
            latest,
            threshold.window_days,
        )
        if count >= threshold.count:
            found.append(
                OvercomePattern(
                    error_type=error_type,
                    topic_name=submission.topic_name,
                    count=count,
                    correct=run,
                )
            )
    return found
