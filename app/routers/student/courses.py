import uuid

from fastapi import APIRouter

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.search import Search
from app.core.security import StudentUser
from app.models import TutorSettings
from app.schemas.courses import JoinCourse, StudentCourse
from app.schemas.tutor import StudentTutorSettings
from app.services import courses

router = APIRouter(tags=["student: courses"])


@router.post(
    "/enrolments",
    response_model=StudentCourse,
    responses=error_responses(400, 403, 422),
)
def join_course(
    payload: JoinCourse, student: StudentUser, session: DbSession
) -> StudentCourse:
    enrolment = courses.join_course(session, student, payload.class_code)
    return courses.to_student_course(session, enrolment)


@router.get("/courses", response_model=Page[StudentCourse])
def list_courses(
    student: StudentUser,
    session: DbSession,
    page: Pagination,
    q: Search = None,
    sort: courses.CourseSort = "recent",
) -> Page[StudentCourse]:
    rows, total = courses.list_student_enrolments(
        session, student, page.limit, page.offset, q, sort
    )
    return Page[StudentCourse](
        items=[courses.to_student_course(session, e) for e in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/courses/{course_id}",
    response_model=StudentCourse,
    responses=error_responses(403, 404),
)
def read_course(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> StudentCourse:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return courses.to_student_course(session, enrolment)


@router.post(
    "/courses/{course_id}/disclosure",
    response_model=StudentCourse,
    responses=error_responses(403, 404),
    summary="Acknowledge the AI tutor disclosure for this course",
)
def acknowledge_disclosure(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> StudentCourse:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    courses.acknowledge_disclosure(session, enrolment)
    return courses.to_student_course(session, enrolment)


@router.get(
    "/courses/{course_id}/tutor-settings",
    response_model=StudentTutorSettings,
    responses=error_responses(403, 404),
    summary="The tutor settings the teacher chose (read only)",
)
def read_tutor_settings(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> StudentTutorSettings:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    row = session.get(TutorSettings, enrolment.course_id)
    return StudentTutorSettings.model_validate(row, from_attributes=True)
