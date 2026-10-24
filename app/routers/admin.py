from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.security import require_role
from app.integrations.auth_admin import AuthAdminClient, get_auth_admin
from app.schemas.admin import (
    AdminCourse,
    CreatedAccount,
    PseudonymousBatch,
    PseudonymousBatchCreate,
    TeacherCreate,
)
from app.schemas.admin import (
    AdminUser as AdminUserOut,
)
from app.schemas.review import EvaluationItem
from app.services import accounts, review

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role("admin"))],
    responses=error_responses(401, 403),
)

AuthAdmin = Annotated[AuthAdminClient, Depends(get_auth_admin)]


@router.get("/users", response_model=Page[AdminUserOut])
def list_users(
    session: DbSession,
    page: Pagination,
    role: Annotated[Literal["admin", "teacher", "student"] | None, Query()] = None,
    status: Annotated[Literal["active", "disabled"] | None, Query()] = None,
) -> Page[AdminUserOut]:
    rows, total = accounts.list_users(session, role, status, page.limit, page.offset)
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


@router.get("/courses", response_model=Page[AdminCourse])
def list_courses(session: DbSession, page: Pagination) -> Page[AdminCourse]:
    items, total = accounts.list_courses(session, page.limit, page.offset)
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
