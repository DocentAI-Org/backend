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
from app.services import pedagogy


def focus(
    session: Session, settings: Settings, course_id: uuid.UUID, student_id: uuid.UUID
) -> Adaptation | None:
    """The most frequent error type in the window, if repeated enough (the course's
    repeated-mistake criteria, specs/015); ties go to the most recent. None when the
    course turns adaptation off."""
    criteria = pedagogy.in_effect(session, course_id).criteria
    if not criteria.adaptation.enabled:
        return None
    threshold = criteria.repeated_mistakes
    since = datetime.now(UTC) - timedelta(days=threshold.window_days)
    count = func.count(LearningRecordEntry.id)
    row = session.execute(
        select(LearningRecordEntry.error_type, count)
        .where(
            LearningRecordEntry.course_id == course_id,
            LearningRecordEntry.student_id == student_id,
            LearningRecordEntry.created_at >= since,
        )
        .group_by(LearningRecordEntry.error_type)
        .having(count >= threshold.count)
        .order_by(count.desc(), func.max(LearningRecordEntry.created_at).desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return Adaptation(
        error_type=row[0], count=row[1], window_days=threshold.window_days
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
