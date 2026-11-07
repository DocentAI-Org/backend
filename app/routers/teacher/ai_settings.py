import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import TeacherUser
from app.llm.catalog import Catalog, get_catalog
from app.schemas.ai_settings import AIModels, CourseAISettings, CourseOverrides
from app.services import ai_settings, courses

router = APIRouter(prefix="/courses/{course_id}", tags=["teacher: AI settings"])

ModelCatalog = Annotated[Catalog, Depends(get_catalog)]


@router.get(
    "/ai-settings",
    response_model=CourseAISettings,
    responses=error_responses(404),
    summary="The course's AI settings: inherited, its own and those in effect",
)
def read_ai_settings(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> CourseAISettings:
    course = courses.get_owned_course(session, course_id, teacher)
    return ai_settings.for_course(session, get_settings(), course)


@router.put(
    "/ai-settings",
    response_model=CourseAISettings,
    responses=error_responses(404, 422),
    summary="Set the course's own models, limits and retrieval; null inherits",
)
def update_ai_settings(
    course_id: uuid.UUID,
    payload: CourseOverrides,
    teacher: TeacherUser,
    session: DbSession,
    catalog: ModelCatalog,
) -> CourseAISettings:
    course = courses.get_owned_course(session, course_id, teacher)
    return ai_settings.update_course(
        session, get_settings(), catalog, course, payload, teacher
    )


@router.get(
    "/ai-models",
    response_model=AIModels,
    responses=error_responses(404),
    summary="The models the course can use, by source (specs/019)",
)
def list_ai_models(
    course_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    catalog: ModelCatalog,
) -> AIModels:
    courses.get_owned_course(session, course_id, teacher)
    return AIModels(sources=catalog.sources())
