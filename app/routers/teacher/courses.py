import uuid

from fastapi import APIRouter, Response

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.security import TeacherUser
from app.schemas.courses import (
    ClassCodeUpdate,
    CourseCreate,
    CourseStudent,
    CourseUpdate,
    TeacherCourse,
)
from app.services import courses

router = APIRouter(prefix="/courses", tags=["teacher: courses"])


@router.post(
    "", status_code=201, response_model=TeacherCourse, responses=error_responses(422)
)
def create_course(
    payload: CourseCreate, teacher: TeacherUser, session: DbSession
) -> TeacherCourse:
    course = courses.create_course(session, teacher, payload.name, payload.description)
    return courses.to_teacher_course(session, course)


@router.get("", response_model=Page[TeacherCourse])
def list_courses(
    teacher: TeacherUser, session: DbSession, page: Pagination
) -> Page[TeacherCourse]:
    rows, total = courses.list_teacher_courses(
        session, teacher, page.limit, page.offset
    )
    return Page[TeacherCourse](
        items=[courses.to_teacher_course(session, c) for c in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/{course_id}", response_model=TeacherCourse, responses=error_responses(404)
)
def read_course(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> TeacherCourse:
    course = courses.get_owned_course(session, course_id, teacher)
    return courses.to_teacher_course(session, course)


@router.patch(
    "/{course_id}", response_model=TeacherCourse, responses=error_responses(404, 422)
)
def update_course(
    course_id: uuid.UUID,
    payload: CourseUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> TeacherCourse:
    course = courses.get_owned_course(session, course_id, teacher)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue
        setattr(course, field, value)
    session.flush()
    return courses.to_teacher_course(session, course)


@router.post(
    "/{course_id}/class-code/regenerate",
    response_model=TeacherCourse,
    responses=error_responses(404),
)
def regenerate_class_code(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> TeacherCourse:
    course = courses.get_owned_course(session, course_id, teacher)
    courses.regenerate_code(session, course)
    return courses.to_teacher_course(session, course)


@router.patch(
    "/{course_id}/class-code",
    response_model=TeacherCourse,
    responses=error_responses(404, 422),
)
def update_class_code(
    course_id: uuid.UUID,
    payload: ClassCodeUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> TeacherCourse:
    course = courses.get_owned_course(session, course_id, teacher)
    course.class_code_active = payload.active
    session.flush()
    return courses.to_teacher_course(session, course)


@router.get(
    "/{course_id}/students",
    response_model=Page[CourseStudent],
    responses=error_responses(404),
)
def list_students(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession, page: Pagination
) -> Page[CourseStudent]:
    course = courses.get_owned_course(session, course_id, teacher)
    items, total = courses.list_students(session, course, page.limit, page.offset)
    return Page[CourseStudent](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.delete(
    "/{course_id}/students/{student_id}",
    status_code=204,
    responses=error_responses(404),
)
def revoke_student(
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    courses.revoke_enrolment(session, course, student_id)
    return Response(status_code=204)
