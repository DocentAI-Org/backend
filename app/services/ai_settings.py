"""AI settings (specs/019): each group comes from the course, else the study, else the
server's environment; models are resolved per task the same way."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Route, Settings, Task
from app.core.errors import ApiError
from app.llm.catalog import Catalog
from app.llm.credentials import CredentialAccess
from app.models import AISettings, Course, LLMCredential, Profile
from app.schemas import ai_settings as schemas
from app.schemas.ai_settings import COUNTED_TASKS, ModelSource
from app.services import llm_credentials

TASKS: tuple[Task, ...] = ("tutor", "feedback", "review", "questions")


@dataclass(frozen=True)
class InEffect:
    models: dict[Task, schemas.ResolvedModel]
    limits: schemas.Limits
    retrieval: schemas.Retrieval
    ceiling: schemas.Ceiling
    credentials: dict[uuid.UUID, CredentialAccess] = field(default_factory=dict)

    def route(self, task: Task) -> Route:
        model = self.models[task]
        return Route(
            model.provider,
            model.model,
            model.effort,
            model.temperature,
            model.max_tokens,
            self.credentials[model.credential_id] if model.credential_id else None,
        )


def server_values(settings: Settings) -> schemas.StudyValues:
    def model(task: Task) -> schemas.ResolvedModel:
        route = settings.route(task)
        return schemas.ResolvedModel(
            provider=route.provider,
            model=route.model,
            effort=route.effort,
            origin="server",
        )

    return schemas.StudyValues(
        models={task: model(task) for task in TASKS},
        limits=schemas.Limits(
            messages=None, period="day", counted_tasks=list(COUNTED_TASKS)
        ),
        retrieval=schemas.Retrieval(
            top_k=settings.retrieval_top_k,
            min_similarity=settings.retrieval_min_similarity,
            min_similarity_exercises=settings.retrieval_min_similarity_exercises,
            history_messages=settings.history_max_messages,
        ),
        ceiling=schemas.Ceiling(messages=settings.daily_message_limit),
    )


def _study_row(session: Session) -> AISettings:
    row = session.scalar(select(AISettings).where(AISettings.course_id.is_(None)))
    if row is None:  # pragma: no cover - the migration inserts it
        raise RuntimeError("The study's AI settings are missing.")
    return row


def _course_row(session: Session, course_id: uuid.UUID) -> AISettings | None:
    return session.scalar(select(AISettings).where(AISettings.course_id == course_id))


def _layer(
    base: schemas.StudyValues, row: AISettings | None, origin: schemas.Origin
) -> schemas.StudyValues:
    """`base` with what `row` changes."""
    if row is None:
        return base
    models = dict(base.models)
    for task, choice in row.models.items():
        models[task] = schemas.ResolvedModel(**choice, origin=origin)
    return schemas.StudyValues(
        models=models,
        limits=schemas.Limits(**row.limits) if row.limits else base.limits,
        retrieval=(
            schemas.Retrieval(**row.retrieval) if row.retrieval else base.retrieval
        ),
        ceiling=schemas.Ceiling(**row.ceiling) if row.ceiling else base.ceiling,
    )


def _values(values: schemas.StudyValues) -> schemas.Values:
    return schemas.Values(
        models=values.models, limits=values.limits, retrieval=values.retrieval
    )


def in_effect(session: Session, settings: Settings, course_id: uuid.UUID) -> InEffect:
    study = _layer(server_values(settings), _study_row(session), "study")
    values = _layer(study, _course_row(session, course_id), "course")
    credentials = {}
    for model in values.models.values():
        if model.credential_id and model.credential_id not in credentials:
            row = session.get(LLMCredential, model.credential_id)
            # Deleting a key resets the tasks using it, so it is always there.
            assert row is not None
            credentials[row.id] = llm_credentials.access(settings, row)
    return InEffect(
        values.models, values.limits, values.retrieval, study.ceiling, credentials
    )


def study_ceiling(session: Session, settings: Settings) -> schemas.Ceiling:
    return _layer(server_values(settings), _study_row(session), "study").ceiling


def _overrides(row: AISettings | None) -> dict:
    models = dict.fromkeys(TASKS)
    if row is None:
        return {"models": models, "limits": None, "retrieval": None}
    models.update(row.models)
    return {"models": models, "limits": row.limits, "retrieval": row.retrieval}


def _check_models(sources: list[ModelSource], models: schemas.TaskModels) -> None:
    """Only a model one of the sources offers, through that source's key."""
    for task in TASKS:
        choice: schemas.ModelChoice | None = getattr(models, task)
        if choice is None:
            continue
        source = next(
            (
                s
                for s in sources
                if s.credential_id == choice.credential_id
                and s.provider == choice.provider
            ),
            None,
        )
        if source is None and choice.credential_id is not None:
            raise ApiError(
                422,
                "credential_unavailable",
                "This course cannot use that key.",
                {"task": task},
            )
        if source is None:
            raise ApiError(
                422,
                "provider_unavailable",
                f"The server has no key for {choice.provider}.",
                {"task": task},
            )
        if not source.reachable:
            raise ApiError(
                422,
                "provider_unreachable",
                f"{source.label} does not answer; try again later.",
                {"task": task},
            )
        if choice.model not in {m.id for m in source.models}:
            raise ApiError(
                422,
                "model_unavailable",
                f"{source.label} does not offer {choice.model}.",
                {"task": task},
            )
        if choice.provider == "anthropic" and choice.temperature is not None:
            raise ApiError(
                422,
                "temperature_not_supported",
                "Anthropic models take no temperature.",
                {"task": task},
            )


def _store(
    row: AISettings,
    payload: schemas.StudyOverrides | schemas.CourseOverrides,
    user: Profile,
) -> None:
    row.models = {
        task: choice.model_dump(mode="json")
        for task in TASKS
        if (choice := getattr(payload.models, task)) is not None
    }
    row.limits = payload.limits.model_dump() if payload.limits else None
    row.retrieval = payload.retrieval.model_dump() if payload.retrieval else None
    row.notices = []
    row.updated_at = func.clock_timestamp()
    row.updated_by = user.id


def _reset(
    session: Session,
    keep: Callable[[dict], bool],
    reason: str,
) -> None:
    """Every task whose model `keep` rejects goes back to the inherited one, with a
    notice."""
    at = datetime.now(UTC).isoformat()
    for row in session.scalars(select(AISettings)):
        removed = {t: c for t, c in row.models.items() if not keep(c)}
        if not removed:
            continue
        row.models = {t: c for t, c in row.models.items() if t not in removed}
        row.notices = [
            *row.notices,
            *(
                {"task": t, "model": c["model"], "reason": reason, "at": at}
                for t, c in removed.items()
            ),
        ]
    session.flush()


def withdraw(
    session: Session, credential_id: uuid.UUID, offered: set[str], reason: str
) -> None:
    """Tasks using the key with a model it no longer offers (any, when deleted)."""
    _reset(
        session,
        lambda c: c.get("credential_id") != str(credential_id) or c["model"] in offered,
        reason,
    )


def _disable_teacher_keys(session: Session) -> None:
    own = {
        str(i)
        for i in session.scalars(
            select(LLMCredential.id).where(LLMCredential.course_id.is_not(None))
        )
    }
    _reset(
        session, lambda c: c.get("credential_id") not in own, "teacher_keys_disabled"
    )


def study(session: Session, settings: Settings) -> schemas.StudyAISettings:
    row = _study_row(session)
    server = server_values(settings)
    return schemas.StudyAISettings(
        server=server,
        study=schemas.StudyOverrides.model_validate(
            {
                **_overrides(row),
                "ceiling": row.ceiling,
                "allow_teacher_keys": row.allow_teacher_keys,
            }
        ),
        effective=_layer(server, row, "study"),
        notices=row.notices,
        updated_at=row.updated_at,
    )


def update_study(
    session: Session,
    settings: Settings,
    catalog: Catalog,
    payload: schemas.StudyOverrides,
    admin: Profile,
) -> schemas.StudyAISettings:
    _check_models(llm_credentials.sources(session, settings, catalog), payload.models)
    row = _study_row(session)
    _store(row, payload, admin)
    row.ceiling = payload.ceiling.model_dump() if payload.ceiling else None
    if row.allow_teacher_keys and not payload.allow_teacher_keys:
        _disable_teacher_keys(session)
    row.allow_teacher_keys = payload.allow_teacher_keys
    session.flush()
    session.refresh(row)
    return study(session, settings)


def for_course(
    session: Session, settings: Settings, course: Course
) -> schemas.CourseAISettings:
    study_row = _study_row(session)
    study_values = _layer(server_values(settings), study_row, "study")
    own = _course_row(session, course.id)
    return schemas.CourseAISettings(
        inherited=_values(study_values),
        course=schemas.CourseOverrides.model_validate(_overrides(own)),
        effective=_values(_layer(study_values, own, "course")),
        ceiling=study_values.ceiling,
        allow_teacher_keys=study_row.allow_teacher_keys,
        notices=own.notices if own else [],
    )


def teacher_keys_allowed(session: Session) -> bool:
    return _study_row(session).allow_teacher_keys


def course_sources(
    session: Session, settings: Settings, catalog: Catalog, course_id: uuid.UUID
) -> list[ModelSource]:
    return llm_credentials.sources(
        session, settings, catalog, course_id, teacher_keys_allowed(session)
    )


def update_course(
    session: Session,
    settings: Settings,
    catalog: Catalog,
    course: Course,
    payload: schemas.CourseOverrides,
    teacher: Profile,
) -> schemas.CourseAISettings:
    _check_models(course_sources(session, settings, catalog, course.id), payload.models)
    own = _course_row(session, course.id)
    if own is None:
        own = AISettings(course_id=course.id)
        session.add(own)
    _store(own, payload, teacher)
    session.flush()
    return for_course(session, settings, course)
