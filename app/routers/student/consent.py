from fastapi import APIRouter

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.security import StudentUser
from app.schemas.consent import Consent, ConsentEvent
from app.services import consent

router = APIRouter(prefix="/consent", tags=["student: consent"])


@router.get("", response_model=Consent)
def read_consent(student: StudentUser, session: DbSession) -> Consent:
    return consent.status(session, get_settings(), student.id)


@router.post("", response_model=Consent, summary="Give study consent (current version)")
def give_consent(student: StudentUser, session: DbSession) -> Consent:
    return consent.give(session, get_settings(), student.id)


@router.delete("", response_model=Consent, summary="Revoke study consent")
def revoke_consent(student: StudentUser, session: DbSession) -> Consent:
    return consent.revoke(session, get_settings(), student.id)


@router.get("/history", response_model=list[ConsentEvent])
def read_history(student: StudentUser, session: DbSession) -> list[ConsentEvent]:
    return consent.history(session, student.id)
