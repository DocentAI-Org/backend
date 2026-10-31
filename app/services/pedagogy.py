"""Pedagogical criteria (specs/015): the study defaults, each course's overrides per
group, and the criteria in effect for a course, which every feature reads."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Course, PedagogyCriteria, Profile
from app.schemas import pedagogy as schemas
from app.schemas.pedagogy import GROUPS


@dataclass(frozen=True)
class InEffect:
    criteria: schemas.Criteria
    provisional: bool


def _defaults(session: Session) -> PedagogyCriteria:
    row = session.scalar(
        select(PedagogyCriteria).where(PedagogyCriteria.course_id.is_(None))
    )
    if row is None:  # pragma: no cover - the migration inserts it
        raise RuntimeError("The study's pedagogical criteria are missing.")
    return row


def _course_row(session: Session, course_id: uuid.UUID) -> PedagogyCriteria | None:
    return session.scalar(
        select(PedagogyCriteria).where(PedagogyCriteria.course_id == course_id)
    )


def _criteria(row: PedagogyCriteria) -> schemas.Criteria:
    return schemas.Criteria.model_validate({g: getattr(row, g) for g in GROUPS})


def in_effect(session: Session, course_id: uuid.UUID) -> InEffect:
    """The course's own group where it has one, the study's otherwise."""
    defaults = _defaults(session)
    own = _course_row(session, course_id)
    values = {
        g: (getattr(own, g) if own and getattr(own, g) is not None else None)
        or getattr(defaults, g)
        for g in GROUPS
    }
    return InEffect(schemas.Criteria.model_validate(values), defaults.provisional)


def study(session: Session) -> schemas.StudyCriteria:
    row = _defaults(session)
    return schemas.StudyCriteria(
        criteria=_criteria(row), provisional=row.provisional, updated_at=row.updated_at
    )


def update_study(
    session: Session, payload: schemas.StudyCriteriaUpdate, admin: Profile
) -> schemas.StudyCriteria:
    row = _defaults(session)
    for group in GROUPS:
        setattr(row, group, getattr(payload.criteria, group).model_dump())
    row.provisional = payload.provisional
    row.updated_at = func.clock_timestamp()
    row.updated_by = admin.id
    session.flush()
    session.refresh(row)
    return study(session)


def for_course(session: Session, course: Course) -> schemas.CourseCriteria:
    own = _course_row(session, course.id)
    current = in_effect(session, course.id)
    return schemas.CourseCriteria(
        study=_criteria(_defaults(session)),
        provisional=current.provisional,
        custom={g: bool(own and getattr(own, g) is not None) for g in GROUPS},
        effective=current.criteria,
    )


def update_course(
    session: Session,
    course: Course,
    payload: schemas.CourseCriteriaUpdate,
    teacher: Profile,
) -> schemas.CourseCriteria:
    own = _course_row(session, course.id)
    if own is None:
        own = PedagogyCriteria(course_id=course.id)
        session.add(own)
    for group in GROUPS:
        value = getattr(payload, group)
        setattr(own, group, value.model_dump() if value else None)
    own.updated_at = func.clock_timestamp()
    own.updated_by = teacher.id
    session.flush()
    return for_course(session, course)
