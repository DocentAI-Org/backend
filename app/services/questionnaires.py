"""Study questionnaires (P4, specs/012): the admin lists links to an external tool;
students and teachers see the open ones for them."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import not_found
from app.models import Profile, Questionnaire
from app.schemas import questionnaires as schemas
from app.services import consent
from app.services.study_export import study_ref

PLACEHOLDERS = ("{study_ref}", "%7Bstudy_ref%7D", "%7bstudy_ref%7d")


def list_all(session: Session) -> list[Questionnaire]:
    return list(
        session.scalars(select(Questionnaire).order_by(Questionnaire.created_at.desc()))
    )


def create(session: Session, payload: schemas.QuestionnaireCreate) -> Questionnaire:
    questionnaire = Questionnaire(
        title=payload.title, url=payload.url, audience=payload.audience
    )
    session.add(questionnaire)
    session.flush()
    session.refresh(questionnaire)
    return questionnaire


def _get(session: Session, questionnaire_id: uuid.UUID) -> Questionnaire:
    questionnaire = session.get(Questionnaire, questionnaire_id)
    if questionnaire is None:
        raise not_found("Questionnaire")
    return questionnaire


def update(
    session: Session,
    questionnaire_id: uuid.UUID,
    payload: schemas.QuestionnaireUpdate,
) -> Questionnaire:
    questionnaire = _get(session, questionnaire_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(questionnaire, field, value)
    questionnaire.updated_at = func.clock_timestamp()
    session.flush()
    session.refresh(questionnaire)
    return questionnaire


def delete(session: Session, questionnaire_id: uuid.UUID) -> None:
    session.delete(_get(session, questionnaire_id))
    session.flush()


def _resolve(url: str, code: str) -> str:
    for placeholder in PLACEHOLDERS:
        url = url.replace(placeholder, code)
    return url


def for_user(
    session: Session, settings: Settings, user: Profile
) -> list[schemas.MyQuestionnaire]:
    """Open questionnaires for the caller's role; students only while they consent."""
    if user.role not in ("student", "teacher"):
        return []
    if user.role == "student" and not consent.status(session, settings, user.id).given:
        return []
    code = study_ref(settings, user.id) if user.role == "student" else ""
    rows = session.scalars(
        select(Questionnaire)
        .where(Questionnaire.audience == user.role, Questionnaire.status == "open")
        .order_by(Questionnaire.created_at.desc())
    )
    return [
        schemas.MyQuestionnaire(id=q.id, title=q.title, url=_resolve(q.url, code))
        for q in rows
    ]
