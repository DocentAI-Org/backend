"""Explanations adapted to the student (S8, specs/013, provisional): the error type a
student repeats most in a course, and the note that asks the model to mind it."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.prompts import load_labels
from app.models import ErrorType, LearningRecordEntry
from app.schemas.chat import Adaptation
from app.services import overcome, pedagogy


def focus(
    session: Session, settings: Settings, course_id: uuid.UUID, student_id: uuid.UUID
) -> Adaptation | None:
    """The most frequent error type in the window, if repeated enough (the course's
    repeated-mistake criteria, specs/015), leaving out the patterns already overcome
    (specs/023); ties go to the most recent. None when the course turns adaptation
    off."""
    criteria = pedagogy.in_effect(session, course_id).criteria
    if not criteria.adaptation.enabled:
        return None
    threshold = criteria.repeated_mistakes
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
            LearningRecordEntry.course_id == course_id,
            LearningRecordEntry.student_id == student_id,
            LearningRecordEntry.created_at >= since,
        )
        .group_by(
            LearningRecordEntry.error_type,
            LearningRecordEntry.topic_id,
            LearningRecordEntry.topic_name,
        )
    ).all()
    # Patterns (error type and topic) already overcome do not count (specs/023).
    totals: dict[str, tuple[int, datetime]] = {}
    for error_type, topic_id, topic_name, times, last in rows:
        if (
            overcome.correct_run(
                session, course_id, student_id, topic_id, topic_name, last
            )
            >= threshold.overcome_after
        ):
            continue
        total, newest = totals.get(error_type, (0, last))
        totals[error_type] = (total + times, max(newest, last))
    repeated = [(t, n, last) for t, (n, last) in totals.items() if n >= threshold.count]
    if not repeated:
        return None
    error_type, times, _ = max(repeated, key=lambda r: (r[1], r[2]))
    return Adaptation(
        error_type=error_type, count=times, window_days=threshold.window_days
    )


def prompt_note(
    session: Session, settings: Settings, adaptation: Adaptation | None
) -> str | None:
    """Only the error type and the count reach the model: nothing about who it is."""
    if adaptation is None:
        return None
    error_type = session.get(ErrorType, adaptation.error_type)
    if error_type is None:
        return None
    return load_labels("policies", settings.tutor_language)["adaptation"].format(
        count=adaptation.count,
        days=adaptation.window_days,
        label=error_type.label_es,
        description=error_type.description_es.rstrip("."),
    )
