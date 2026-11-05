"""Courses, class codes and enrolment (T1), plus the ownership checks every
course-scoped endpoint relies on (constitution II)."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import case, delete, exists, func, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError, forbidden, not_found
from app.core.search import matches
from app.models import Course, CourseFavorite, Enrolment, Profile, TutorSettings
from app.schemas.courses import CourseStudent, StudentCourse, TeacherCourse
from app.services.accounts import random_code


def _new_class_code(session: Session) -> str:
    while True:
        code = f"{random_code(3)}-{random_code(4)}"
        if session.scalar(select(Course.id).where(Course.class_code == code)) is None:
            return code


def get_owned_course(
    session: Session, course_id: uuid.UUID, teacher: Profile
) -> Course:
    course = session.get(Course, course_id)
    if course is None or course.teacher_id != teacher.id:
        raise not_found("Course")
    return course


def get_active_enrolment(
    session: Session, course_id: uuid.UUID, student: Profile
) -> Enrolment:
    enrolment = session.scalar(
        select(Enrolment).where(
            Enrolment.course_id == course_id, Enrolment.student_id == student.id
        )
    )
    if enrolment is None:
        raise not_found("Course")
    if enrolment.status != "active":
        raise ApiError(
            403, "enrolment_revoked", "Your enrolment in this course was revoked."
        )
    return enrolment


def _student_count(session: Session, course_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count(Enrolment.id)).where(
                Enrolment.course_id == course_id, Enrolment.status == "active"
            )
        )
        or 0
    )


CourseSort = Literal["recent", "name"]
StudentSort = Literal["joined", "name"]


def _starred(user_id: uuid.UUID):
    """True for the courses `user_id` starred (specs/016)."""
    return exists().where(
        CourseFavorite.user_id == user_id, CourseFavorite.course_id == Course.id
    )


def _favorite_filter(user_id: uuid.UUID, favorite: bool | None):
    """Only starred courses (True), only the others (False) or all (None)."""
    if favorite is None:
        return true()
    return _starred(user_id) if favorite else ~_starred(user_id)


def _is_favorite(session: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    return session.get(CourseFavorite, (user_id, course_id)) is not None


def to_teacher_course(session: Session, course: Course) -> TeacherCourse:
    return TeacherCourse(
        id=course.id,
        name=course.name,
        description=course.description,
        class_code=course.class_code,
        class_code_active=course.class_code_active,
        invitation_path=f"/join/{course.class_code}",
        student_count=_student_count(session, course.id),
        created_at=course.created_at,
        is_favorite=_is_favorite(session, course.teacher_id, course.id),
    )


def to_student_course(session: Session, enrolment: Enrolment) -> StudentCourse:
    course = enrolment.course
    return StudentCourse(
        id=course.id,
        name=course.name,
        description=course.description,
        teacher_name=course.teacher.display_name,
        joined_at=enrolment.joined_at,
        disclosure_acknowledged=enrolment.disclosure_acknowledged_at is not None,
        is_favorite=_is_favorite(session, enrolment.student_id, course.id),
    )


def create_course(
    session: Session, teacher: Profile, name: str, description: str | None
) -> Course:
    course = Course(
        teacher_id=teacher.id,
        name=name,
        description=description,
        class_code=_new_class_code(session),
    )
    session.add(course)
    session.flush()
    session.add(TutorSettings(course_id=course.id))
    session.flush()
    session.refresh(course)
    return course


def _course_order(user_id: uuid.UUID, sort: CourseSort, recent):
    """Starred courses first, then the chosen order (specs/016)."""
    starred_first = case((_starred(user_id), 0), else_=1)
    if sort == "name":
        return starred_first, func.lower(Course.name), Course.id
    return starred_first, recent.desc(), Course.id


def list_teacher_courses(
    session: Session,
    teacher: Profile,
    limit: int,
    offset: int,
    q: str | None = None,
    sort: CourseSort = "recent",
    favorite: bool | None = None,
) -> tuple[list[Course], int]:
    query = select(Course).where(
        Course.teacher_id == teacher.id,
        matches(q, Course.name, Course.description),
        _favorite_filter(teacher.id, favorite),
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(*_course_order(teacher.id, sort, Course.created_at))
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def regenerate_code(session: Session, course: Course) -> Course:
    course.class_code = _new_class_code(session)
    course.class_code_active = True
    session.flush()
    return course


def list_students(
    session: Session,
    course: Course,
    limit: int,
    offset: int,
    q: str | None = None,
    sort: StudentSort = "joined",
) -> tuple[list[CourseStudent], int]:
    query = (
        select(Enrolment)
        .join(Profile, Profile.id == Enrolment.student_id)
        .where(Enrolment.course_id == course.id, matches(q, Profile.display_name))
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    order = (
        (func.lower(Profile.display_name), Enrolment.id)
        if sort == "name"
        else (Enrolment.joined_at, Enrolment.id)
    )
    rows = session.scalars(query.order_by(*order).limit(limit).offset(offset)).all()
    items = [
        CourseStudent(
            student_id=e.student_id,
            display_name=e.student.display_name,
            joined_at=e.joined_at,
            status=e.status,  # type: ignore[arg-type]
        )
        for e in rows
    ]
    return items, total


def get_course_enrolment(
    session: Session, course: Course, student_id: uuid.UUID
) -> Enrolment:
    """A student of the teacher's course, active or revoked."""
    enrolment = session.scalar(
        select(Enrolment).where(
            Enrolment.course_id == course.id, Enrolment.student_id == student_id
        )
    )
    if enrolment is None:
        raise not_found("Student")
    return enrolment


def revoke_enrolment(session: Session, course: Course, student_id: uuid.UUID) -> None:
    enrolment = get_course_enrolment(session, course, student_id)
    enrolment.status = "revoked"
    session.flush()


def join_course(session: Session, student: Profile, class_code: str) -> Enrolment:
    course = session.scalar(
        select(Course).where(Course.class_code == class_code.strip().upper())
    )
    if course is None:
        raise ApiError(400, "class_code_invalid", "This class code is not valid.")
    if not course.class_code_active:
        raise ApiError(400, "class_code_disabled", "This class code is disabled.")
    enrolment = session.scalar(
        select(Enrolment).where(
            Enrolment.course_id == course.id, Enrolment.student_id == student.id
        )
    )
    if enrolment is None:
        enrolment = Enrolment(course_id=course.id, student_id=student.id)
        session.add(enrolment)
        session.flush()
        session.refresh(enrolment)
    elif enrolment.status != "active":
        raise ApiError(
            403, "enrolment_revoked", "Your enrolment in this course was revoked."
        )
    return enrolment


def list_student_enrolments(
    session: Session,
    student: Profile,
    limit: int,
    offset: int,
    q: str | None = None,
    sort: CourseSort = "recent",
    favorite: bool | None = None,
) -> tuple[list[Enrolment], int]:
    teacher = Profile.__table__.alias("teacher")
    query = (
        select(Enrolment)
        .join(Course, Course.id == Enrolment.course_id)
        .join(teacher, teacher.c.id == Course.teacher_id)
        .where(
            Enrolment.student_id == student.id,
            Enrolment.status == "active",
            matches(q, Course.name, Course.description, teacher.c.display_name),
            _favorite_filter(student.id, favorite),
        )
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(*_course_order(student.id, sort, Enrolment.joined_at))
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def _visible_course(session: Session, user: Profile, course_id: uuid.UUID) -> Course:
    """A course the user teaches or is actively in; others are 404 (specs/016)."""
    course = session.get(Course, course_id)
    if course is not None and user.role == "teacher" and course.teacher_id == user.id:
        return course
    if course is not None and user.role == "student":
        active = session.scalar(
            select(Enrolment.id).where(
                Enrolment.course_id == course_id,
                Enrolment.student_id == user.id,
                Enrolment.status == "active",
            )
        )
        if active is not None:
            return course
    raise not_found("Course")


def star_course(session: Session, user: Profile, course_id: uuid.UUID) -> None:
    if user.role not in ("teacher", "student"):
        raise forbidden()
    _visible_course(session, user, course_id)
    session.execute(
        insert(CourseFavorite)
        .values(user_id=user.id, course_id=course_id)
        .on_conflict_do_nothing()
    )


def unstar_course(session: Session, user: Profile, course_id: uuid.UUID) -> None:
    if user.role not in ("teacher", "student"):
        raise forbidden()
    _visible_course(session, user, course_id)
    session.execute(
        delete(CourseFavorite).where(
            CourseFavorite.user_id == user.id, CourseFavorite.course_id == course_id
        )
    )


def acknowledge_disclosure(session: Session, enrolment: Enrolment) -> Enrolment:
    if enrolment.disclosure_acknowledged_at is None:
        enrolment.disclosure_acknowledged_at = datetime.now(UTC)
        session.flush()
    return enrolment
