import uuid

from fastapi import APIRouter, Response

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import CurrentUser
from app.schemas.me import Me, MeUpdate
from app.schemas.questionnaires import MyQuestionnaire
from app.services import courses, questionnaires

router = APIRouter(prefix="/me", tags=["me"], responses=error_responses(401, 403))


@router.get("", response_model=Me)
def read_me(user: CurrentUser) -> Me:
    return Me.from_profile(user)


@router.patch("", response_model=Me, responses=error_responses(422))
def update_me(payload: MeUpdate, user: CurrentUser, session: DbSession) -> Me:
    user.preferred_language = payload.preferred_language
    session.flush()
    return Me.from_profile(user)


@router.get(
    "/questionnaires",
    response_model=list[MyQuestionnaire],
    summary="Open study questionnaires for the caller (P4, specs/012)",
)
def my_questionnaires(user: CurrentUser, session: DbSession) -> list[MyQuestionnaire]:
    return questionnaires.for_user(session, get_settings(), user)


@router.put(
    "/favorite-courses/{course_id}",
    status_code=204,
    responses=error_responses(404),
    summary="Star a course the caller teaches or is in (specs/016)",
)
def star_course(
    course_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    courses.star_course(session, user, course_id)
    return Response(status_code=204)


@router.delete(
    "/favorite-courses/{course_id}",
    status_code=204,
    responses=error_responses(404),
    summary="Unstar a course (specs/016)",
)
def unstar_course(
    course_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    courses.unstar_course(session, user, course_id)
    return Response(status_code=204)
