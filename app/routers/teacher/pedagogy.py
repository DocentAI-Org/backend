import uuid

from fastapi import APIRouter

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import TeacherUser
from app.schemas.pedagogy import CourseCriteria, CourseCriteriaUpdate
from app.services import courses, pedagogy

router = APIRouter(prefix="/courses/{course_id}", tags=["teacher: pedagogy"])


@router.get(
    "/pedagogy-criteria",
    response_model=CourseCriteria,
    responses=error_responses(404),
    summary="The study's criteria, the course's own groups and those in effect",
)
def read_course_criteria(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> CourseCriteria:
    course = courses.get_owned_course(session, course_id, teacher)
    return pedagogy.for_course(session, course)


@router.put(
    "/pedagogy-criteria",
    response_model=CourseCriteria,
    responses=error_responses(404, 422),
    summary="Set the course's own groups; null keeps the study's (specs/015)",
)
def update_course_criteria(
    course_id: uuid.UUID,
    payload: CourseCriteriaUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> CourseCriteria:
    course = courses.get_owned_course(session, course_id, teacher)
    return pedagogy.update_course(session, course, payload, teacher)
