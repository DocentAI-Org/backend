"""Study consent as an append-only history (specs/002, requirements §4.1)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import ConsentEvent
from app.schemas import consent as schemas


def _latest(session: Session, student_id: uuid.UUID) -> ConsentEvent | None:
    return session.scalar(
        select(ConsentEvent)
        .where(ConsentEvent.student_id == student_id)
        .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc())
        .limit(1)
    )


def status(
    session: Session, settings: Settings, student_id: uuid.UUID
) -> schemas.Consent:
    latest = _latest(session, student_id)
    active = latest is not None and latest.action == "given"
    return schemas.Consent(
        given=active and latest.version == settings.consent_version,
        version=latest.version if active and latest else None,
        given_at=latest.created_at if active and latest else None,
        current_version=settings.consent_version,
    )


def give(
    session: Session, settings: Settings, student_id: uuid.UUID
) -> schemas.Consent:
    if not status(session, settings, student_id).given:
        session.add(
            ConsentEvent(
                student_id=student_id, action="given", version=settings.consent_version
            )
        )
        session.flush()
    return status(session, settings, student_id)


def revoke(
    session: Session, settings: Settings, student_id: uuid.UUID
) -> schemas.Consent:
    latest = _latest(session, student_id)
    if latest is not None and latest.action == "given":
        session.add(
            ConsentEvent(
                student_id=student_id, action="revoked", version=latest.version
            )
        )
        session.flush()
    return status(session, settings, student_id)


def history(session: Session, student_id: uuid.UUID) -> list[schemas.ConsentEvent]:
    rows = session.scalars(
        select(ConsentEvent)
        .where(ConsentEvent.student_id == student_id)
        .order_by(ConsentEvent.created_at, ConsentEvent.id)
    ).all()
    return [
        schemas.ConsentEvent(
            action=e.action, version=e.version, created_at=e.created_at
        )  # type: ignore[arg-type]
        for e in rows
    ]


def require(session: Session, settings: Settings, student_id: uuid.UUID) -> None:
    if not status(session, settings, student_id).given:
        raise ApiError(
            409,
            "consent_required",
            "The student must give study consent for the current version first.",
        )
