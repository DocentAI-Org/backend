import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.search import Search
from app.core.security import AdminUser as AdminProfile
from app.core.security import require_role
from app.integrations.auth_admin import AuthAdminClient, get_auth_admin
from app.llm.catalog import Catalog, get_catalog
from app.schemas.admin import (
    AdminCourse,
    CreatedAccount,
    PseudonymousBatch,
    PseudonymousBatchCreate,
    StudentErasure,
    TeacherCreate,
)
from app.schemas.admin import (
    AdminUser as AdminUserOut,
)
from app.schemas.ai_settings import (
    AIModels,
    ModelSource,
    StudyAISettings,
    StudyOverrides,
)
from app.schemas.llm_credentials import (
    Credential,
    CredentialCreate,
    CredentialUpdate,
    StudyCredentials,
)
from app.schemas.pedagogy import StudyCriteria, StudyCriteriaUpdate
from app.schemas.questionnaires import (
    Questionnaire,
    QuestionnaireCreate,
    QuestionnaireUpdate,
)
from app.schemas.review import EvaluationItem
from app.services import (
    accounts,
    ai_settings,
    erasure,
    llm_credentials,
    pedagogy,
    questionnaires,
    review,
    study_export,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role("admin"))],
    responses=error_responses(401, 403),
)

AuthAdmin = Annotated[AuthAdminClient, Depends(get_auth_admin)]
ModelCatalog = Annotated[Catalog, Depends(get_catalog)]


@router.get("/users", response_model=Page[AdminUserOut])
def list_users(
    session: DbSession,
    page: Pagination,
    role: Annotated[Literal["admin", "teacher", "student"] | None, Query()] = None,
    status: Annotated[Literal["active", "disabled"] | None, Query()] = None,
    q: Search = None,
    sort: accounts.AdminSort = "recent",
) -> Page[AdminUserOut]:
    rows, total = accounts.list_users(
        session, role, status, page.limit, page.offset, q, sort
    )
    return Page[AdminUserOut](
        items=[AdminUserOut.from_profile(p) for p in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/teachers",
    status_code=201,
    response_model=CreatedAccount,
    responses=error_responses(409, 422, 503),
)
def create_teacher(
    payload: TeacherCreate, session: DbSession, auth_admin: AuthAdmin
) -> CreatedAccount:
    profile, password = accounts.create_teacher(
        session, auth_admin, payload.email, payload.display_name, payload.password
    )
    return CreatedAccount(
        user=AdminUserOut.from_profile(profile), initial_password=password
    )


@router.post(
    "/students/pseudonymous",
    status_code=201,
    response_model=PseudonymousBatch,
    responses=error_responses(422, 503),
)
def create_pseudonymous_students(
    payload: PseudonymousBatchCreate, session: DbSession, auth_admin: AuthAdmin
) -> PseudonymousBatch:
    created = accounts.create_pseudonymous_students(
        session, auth_admin, get_settings(), payload.count
    )
    return PseudonymousBatch(accounts=created)


@router.delete(
    "/students/{student_id}",
    response_model=StudentErasure,
    responses=error_responses(404, 409, 503),
    summary="Erase a student and everything linked to them (spec 017)",
)
def erase_student(
    student_id: uuid.UUID, session: DbSession, auth_admin: AuthAdmin
) -> StudentErasure:
    return erasure.erase_student(session, auth_admin, get_settings(), student_id)


@router.get("/courses", response_model=Page[AdminCourse])
def list_courses(
    session: DbSession,
    page: Pagination,
    q: Search = None,
    sort: accounts.AdminSort = "recent",
) -> Page[AdminCourse]:
    items, total = accounts.list_courses(session, page.limit, page.offset, q, sort)
    return Page[AdminCourse](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    "/evaluation-set",
    response_model=Page[EvaluationItem],
    summary="Teacher flags and corrections for the evaluation set (no student data)",
)
def evaluation_set(session: DbSession, page: Pagination) -> Page[EvaluationItem]:
    items, total = review.evaluation_set(session, page.limit, page.offset)
    return Page[EvaluationItem](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    "/study-export",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/zip": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
    summary="Pseudonymised study data of consenting students, as a ZIP of CSV files",
)
def export_study_data(
    session: DbSession, course_id: uuid.UUID | None = None
) -> Response:
    content = study_export.build(session, get_settings(), course_id)
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="docentai-study-export.zip"'
        },
    )


@router.get(
    "/questionnaires",
    response_model=list[Questionnaire],
    summary="Study questionnaires (P4, specs/012)",
)
def list_questionnaires(session: DbSession) -> list[Questionnaire]:
    return [Questionnaire.model_validate(q) for q in questionnaires.list_all(session)]


@router.post(
    "/questionnaires",
    status_code=201,
    response_model=Questionnaire,
    responses=error_responses(422),
)
def create_questionnaire(
    payload: QuestionnaireCreate, session: DbSession
) -> Questionnaire:
    return Questionnaire.model_validate(questionnaires.create(session, payload))


@router.patch(
    "/questionnaires/{questionnaire_id}",
    response_model=Questionnaire,
    responses=error_responses(404, 422),
)
def update_questionnaire(
    questionnaire_id: uuid.UUID, payload: QuestionnaireUpdate, session: DbSession
) -> Questionnaire:
    return Questionnaire.model_validate(
        questionnaires.update(session, questionnaire_id, payload)
    )


@router.delete(
    "/questionnaires/{questionnaire_id}",
    status_code=204,
    response_class=Response,
    responses=error_responses(404),
)
def delete_questionnaire(questionnaire_id: uuid.UUID, session: DbSession) -> Response:
    questionnaires.delete(session, questionnaire_id)
    return Response(status_code=204)


@router.get(
    "/pedagogy-criteria",
    response_model=StudyCriteria,
    summary="The study's default pedagogical criteria (specs/015)",
)
def read_study_criteria(session: DbSession) -> StudyCriteria:
    return pedagogy.study(session)


@router.put(
    "/pedagogy-criteria",
    response_model=StudyCriteria,
    responses=error_responses(422),
    summary="Set the defaults for every course without its own values",
)
def update_study_criteria(
    payload: StudyCriteriaUpdate, admin: AdminProfile, session: DbSession
) -> StudyCriteria:
    return pedagogy.update_study(session, payload, admin)


@router.get(
    "/ai-settings",
    response_model=StudyAISettings,
    summary="The study's AI settings and the server's values they change (specs/019)",
)
def read_ai_settings(session: DbSession) -> StudyAISettings:
    return ai_settings.study(session, get_settings())


@router.put(
    "/ai-settings",
    response_model=StudyAISettings,
    responses=error_responses(422),
    summary="Set the AI settings of every course without its own; null inherits",
)
def update_ai_settings(
    payload: StudyOverrides,
    admin: AdminProfile,
    session: DbSession,
    catalog: ModelCatalog,
) -> StudyAISettings:
    return ai_settings.update_study(session, get_settings(), catalog, payload, admin)


@router.get(
    "/ai-models",
    response_model=AIModels,
    summary="The models the server offers, by source",
)
def list_ai_models(session: DbSession, catalog: ModelCatalog) -> AIModels:
    return AIModels(sources=llm_credentials.sources(session, get_settings(), catalog))


@router.get(
    "/llm-credentials",
    response_model=StudyCredentials,
    summary="The server's keys and the study's stored keys (specs/019)",
)
def list_credentials(session: DbSession, catalog: ModelCatalog) -> StudyCredentials:
    return llm_credentials.list_study(session, catalog)


@router.post(
    "/llm-credentials",
    status_code=201,
    response_model=Credential,
    responses=error_responses(409, 422),
    summary="Add a key every course may use; checked with the provider, then encrypted",
)
def create_credential(
    payload: CredentialCreate,
    admin: AdminProfile,
    session: DbSession,
    catalog: ModelCatalog,
) -> Credential:
    return llm_credentials.create(session, get_settings(), catalog, payload, admin)


@router.patch(
    "/llm-credentials/{credential_id}",
    response_model=Credential,
    responses=error_responses(404, 422),
    summary="Rename a key or choose the models courses may use",
)
def update_credential(
    credential_id: uuid.UUID, payload: CredentialUpdate, session: DbSession
) -> Credential:
    row = llm_credentials.get(session, credential_id)
    return llm_credentials.update_study(session, row, payload)


@router.delete(
    "/llm-credentials/{credential_id}",
    status_code=204,
    responses=error_responses(404),
    summary="Delete a key; the courses using it go back to the inherited model",
)
def delete_credential(credential_id: uuid.UUID, session: DbSession) -> Response:
    llm_credentials.delete(session, llm_credentials.get(session, credential_id))
    return Response(status_code=204)


@router.get(
    "/llm-credentials/{credential_id}/models",
    response_model=ModelSource,
    responses=error_responses(404, 409),
    summary="Every model the key's account offers, to choose those courses may use",
)
def list_credential_models(
    credential_id: uuid.UUID, session: DbSession, catalog: ModelCatalog
) -> ModelSource:
    row = llm_credentials.get(session, credential_id)
    return llm_credentials.all_models(get_settings(), catalog, row)
