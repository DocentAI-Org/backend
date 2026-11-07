"""Keys for commercial models stored in the app (specs/019): the study's, offered to
every course, and a teacher's own for one course when the admin allows it. Keys are
checked with the provider, encrypted, and never returned."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Provider, Settings
from app.core.errors import ApiError, not_found
from app.llm.catalog import Catalog
from app.llm.credentials import CredentialAccess, decrypt, encrypt
from app.models import LLMCredential, Profile
from app.schemas import llm_credentials as schemas
from app.schemas.ai_settings import ModelSource
from app.services import ai_settings

# The client each kind of key talks through.
CHAT_PROVIDER: dict[str, Provider] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "openai_compatible": "openai",
}


def _master(settings: Settings) -> str:
    if not settings.llm_credentials_key:
        raise ApiError(
            409,
            "credentials_not_configured",
            "The server has no LLM_CREDENTIALS_KEY, so keys cannot be stored.",
        )
    return settings.llm_credentials_key


def access(settings: Settings, row: LLMCredential) -> CredentialAccess:
    return CredentialAccess(
        row.id,
        CHAT_PROVIDER[row.provider],
        row.label,
        row.base_url,
        decrypt(_master(settings), row.encrypted_key),
    )


def view(row: LLMCredential) -> schemas.Credential:
    return schemas.Credential(
        id=row.id,
        provider=row.provider,  # type: ignore[arg-type]
        label=row.label,
        base_url=row.base_url,
        key_hint=row.key_hint,
        scope="study" if row.course_id is None else "course",
        offered_models=row.offered_models,
        created_at=row.created_at,
    )


def _rows(session: Session, course_id: uuid.UUID | None) -> list[LLMCredential]:
    where = (
        LLMCredential.course_id.is_(None)
        if course_id is None
        else LLMCredential.course_id == course_id
    )
    return list(
        session.scalars(
            select(LLMCredential).where(where).order_by(LLMCredential.created_at)
        )
    )


def create(
    session: Session,
    settings: Settings,
    catalog: Catalog,
    payload: schemas.CredentialCreate,
    user: Profile,
    course_id: uuid.UUID | None = None,
) -> schemas.Credential:
    master = _master(settings)
    key = payload.api_key.get_secret_value()
    base_url = str(payload.base_url).rstrip("/") if payload.base_url else None
    probe = CredentialAccess(
        uuid.uuid4(), CHAT_PROVIDER[payload.provider], payload.label, base_url, key
    )
    checked = catalog.check_key(probe)
    if checked == "rejected":
        raise ApiError(422, "key_rejected", "The provider does not accept this key.")
    if checked == "unreachable":
        raise ApiError(
            422,
            "provider_unreachable",
            "The provider does not answer; try again later.",
        )
    row = LLMCredential(
        course_id=course_id,
        provider=payload.provider,
        label=payload.label,
        base_url=base_url,
        encrypted_key=encrypt(master, key),
        key_hint=f"…{key[-4:]}",
        created_by=user.id,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    return view(row)


def list_study(session: Session, catalog: Catalog) -> schemas.StudyCredentials:
    return schemas.StudyCredentials(
        server=[
            schemas.ServerKey(provider=s.provider, label=s.label)
            for s in catalog.sources()
        ],
        items=[view(row) for row in _rows(session, None)],
    )


def list_course(session: Session, course_id: uuid.UUID) -> list[schemas.Credential]:
    return [view(row) for row in _rows(session, course_id)]


def get(
    session: Session, credential_id: uuid.UUID, course_id: uuid.UUID | None = None
) -> LLMCredential:
    row = session.get(LLMCredential, credential_id)
    if row is None or row.course_id != course_id:
        raise not_found("Credential")
    return row


def update_study(
    session: Session, row: LLMCredential, payload: schemas.CredentialUpdate
) -> schemas.Credential:
    if payload.label is not None:
        row.label = payload.label
    if "offered_models" in payload.model_fields_set:
        row.offered_models = payload.offered_models
        if payload.offered_models is not None:
            ai_settings.withdraw(
                session, row.id, set(payload.offered_models), "model_withdrawn"
            )
    session.flush()
    return view(row)


def delete(session: Session, row: LLMCredential) -> None:
    """The courses using the key go back to the inherited model; the key is deleted."""
    ai_settings.withdraw(session, row.id, set(), "credential_removed")
    session.delete(row)
    session.flush()


def all_models(settings: Settings, catalog: Catalog, row: LLMCredential) -> ModelSource:
    return catalog.credential_models(access(settings, row))


def sources(
    session: Session,
    settings: Settings,
    catalog: Catalog,
    course_id: uuid.UUID | None = None,
    teacher_keys: bool = False,
) -> list[ModelSource]:
    """The server's sources, the study's keys with the models they offer and, for a
    course whose teacher may add keys, its own."""
    found = [s.model_copy(update={"scope": "server"}) for s in catalog.sources()]
    if not settings.llm_credentials_key:
        return found
    for row in _rows(session, None):
        source = catalog.credential_models(access(settings, row))
        offered = row.offered_models
        found.append(
            source.model_copy(
                update={
                    "scope": "study",
                    "models": [
                        m for m in source.models if offered is None or m.id in offered
                    ],
                }
            )
        )
    if course_id is not None and teacher_keys:
        for row in _rows(session, course_id):
            source = catalog.credential_models(access(settings, row))
            found.append(source.model_copy(update={"scope": "course"}))
    return found
