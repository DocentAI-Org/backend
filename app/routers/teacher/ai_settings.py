import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import ApiError, error_responses
from app.core.security import TeacherUser
from app.llm.catalog import Catalog, get_catalog
from app.llm.client import LLMClient, get_llm
from app.schemas.ai_settings import (
    AIModels,
    AITestRequest,
    AITestResult,
    AIUsage,
    CourseAISettings,
    CourseOverrides,
)
from app.schemas.llm_credentials import Credential, CredentialCreate
from app.services import ai_settings, ai_tools, courses, llm_credentials

router = APIRouter(prefix="/courses/{course_id}", tags=["teacher: AI settings"])

ModelCatalog = Annotated[Catalog, Depends(get_catalog)]
LLM = Annotated[LLMClient, Depends(get_llm)]


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
    course = courses.get_owned_course(session, course_id, teacher)
    return AIModels(
        sources=ai_settings.course_sources(session, get_settings(), catalog, course.id)
    )


@router.get(
    "/llm-credentials",
    response_model=list[Credential],
    responses=error_responses(404),
    summary="The teacher's own keys for the course (specs/019)",
)
def list_own_credentials(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> list[Credential]:
    course = courses.get_owned_course(session, course_id, teacher)
    return llm_credentials.list_course(session, course.id)


@router.post(
    "/llm-credentials",
    status_code=201,
    response_model=Credential,
    responses=error_responses(403, 404, 409, 422),
    summary="Add the teacher's own key, if the study allows it; requests then go to "
    "that provider under the teacher's account",
)
def create_own_credential(
    course_id: uuid.UUID,
    payload: CredentialCreate,
    teacher: TeacherUser,
    session: DbSession,
    catalog: ModelCatalog,
) -> Credential:
    course = courses.get_owned_course(session, course_id, teacher)
    if not ai_settings.teacher_keys_allowed(session):
        raise ApiError(
            403, "teacher_keys_disabled", "The study does not allow teachers' own keys."
        )
    return llm_credentials.create(
        session, get_settings(), catalog, payload, teacher, course.id
    )


@router.delete(
    "/llm-credentials/{credential_id}",
    status_code=204,
    responses=error_responses(404),
    summary="Delete the teacher's own key; its tasks go back to the inherited model",
)
def delete_own_credential(
    course_id: uuid.UUID,
    credential_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    llm_credentials.delete(
        session, llm_credentials.get(session, credential_id, course.id)
    )
    return Response(status_code=204)


@router.post(
    "/ai-test",
    response_model=AITestResult,
    responses=error_responses(404, 422, 429, 503),
    summary="Try a message with the given (unsaved) settings; it is not a student "
    "interaction and uses no allowance; at most 20 an hour",
)
def test_ai_settings(
    course_id: uuid.UUID,
    payload: AITestRequest,
    teacher: TeacherUser,
    session: DbSession,
    catalog: ModelCatalog,
    llm: LLM,
) -> AITestResult:
    course = courses.get_owned_course(session, course_id, teacher)
    return ai_tools.test_message(
        session, llm, get_settings(), catalog, course, teacher, payload
    )


@router.get(
    "/ai-usage",
    response_model=AIUsage,
    responses=error_responses(404),
    summary="Messages, tokens and estimated cost per task, and who used most",
)
def read_ai_usage(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> AIUsage:
    course = courses.get_owned_course(session, course_id, teacher)
    return ai_tools.usage(session, get_settings(), course)
