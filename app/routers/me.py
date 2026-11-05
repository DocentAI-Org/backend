import uuid

from fastapi import APIRouter, Response

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import CurrentUser
from app.schemas.course_tags import CourseTag, CourseTagCreate, CourseTagUpdate
from app.schemas.me import Me, MeUpdate
from app.schemas.questionnaires import MyQuestionnaire
from app.services import course_tags, courses, questionnaires

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


# --- Tags of one's own on courses (specs/016 US4) -----------------------------------

TAGS = "/course-tags"


@router.get(TAGS, response_model=list[CourseTag], summary="The caller's course tags")
def list_course_tags(user: CurrentUser, session: DbSession) -> list[CourseTag]:
    return course_tags.list_tags(session, user)


@router.post(
    TAGS, status_code=201, response_model=CourseTag, responses=error_responses(409, 422)
)
def create_course_tag(
    payload: CourseTagCreate, user: CurrentUser, session: DbSession
) -> CourseTag:
    return course_tags.create_tag(session, user, payload)


@router.patch(
    TAGS + "/{tag_id}",
    response_model=CourseTag,
    responses=error_responses(404, 409, 422),
)
def update_course_tag(
    tag_id: uuid.UUID, payload: CourseTagUpdate, user: CurrentUser, session: DbSession
) -> CourseTag:
    return course_tags.update_tag(session, user, tag_id, payload)


@router.delete(TAGS + "/{tag_id}", status_code=204, responses=error_responses(404))
def delete_course_tag(
    tag_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    course_tags.delete_tag(session, user, tag_id)
    return Response(status_code=204)


@router.put(
    TAGS + "/{tag_id}/courses/{course_id}",
    status_code=204,
    responses=error_responses(404),
    summary="Put a tag on a course the caller teaches or is in",
)
def tag_course(
    tag_id: uuid.UUID, course_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    course_tags.tag_course(session, user, tag_id, course_id)
    return Response(status_code=204)


@router.delete(
    TAGS + "/{tag_id}/courses/{course_id}",
    status_code=204,
    responses=error_responses(404),
)
def untag_course(
    tag_id: uuid.UUID, course_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> Response:
    course_tags.untag_course(session, user, tag_id, course_id)
    return Response(status_code=204)
