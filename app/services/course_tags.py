"""Tags of one's own on courses (specs/016 US4): a teacher or student names and colours
their tags and puts them on the courses they teach or are in. Nobody sees anybody
else's."""

import uuid

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError, forbidden, not_found
from app.models import Course, CourseTag, CourseTagLink, Enrolment, Profile
from app.schemas import course_tags as schemas
from app.services.courses import visible_course


def _check_role(user: Profile) -> None:
    if user.role not in ("teacher", "student"):
        raise forbidden()


def _own_tag(session: Session, user: Profile, tag_id: uuid.UUID) -> CourseTag:
    _check_role(user)
    tag = session.get(CourseTag, tag_id)
    if tag is None or tag.user_id != user.id:
        raise not_found("Tag")
    return tag


def _name_free(
    session: Session, user: Profile, name: str, but: uuid.UUID | None = None
):
    clash = select(CourseTag.id).where(
        CourseTag.user_id == user.id, func.lower(CourseTag.name) == name.lower()
    )
    if but is not None:
        clash = clash.where(CourseTag.id != but)
    if session.scalar(clash) is not None:
        raise ApiError(409, "tag_name_taken", "You already have a tag with this name.")


def _visible(user: Profile):
    """True for the courses the user teaches (teacher) or is actively in (student)."""
    if user.role == "teacher":
        return Course.teacher_id == user.id
    return exists().where(
        Enrolment.course_id == Course.id,
        Enrolment.student_id == user.id,
        Enrolment.status == "active",
    )


def _view(session: Session, user: Profile, tag: CourseTag) -> schemas.CourseTag:
    count = session.scalar(
        select(func.count())
        .select_from(CourseTagLink)
        .join(Course, Course.id == CourseTagLink.course_id)
        .where(CourseTagLink.tag_id == tag.id, _visible(user))
    )
    return schemas.CourseTag(
        id=tag.id,
        name=tag.name,
        color=tag.color,  # type: ignore[arg-type]  (the column holds the literal)
        course_count=count or 0,
    )


def list_tags(session: Session, user: Profile) -> list[schemas.CourseTag]:
    _check_role(user)
    tags = session.scalars(
        select(CourseTag)
        .where(CourseTag.user_id == user.id)
        .order_by(func.lower(CourseTag.name), CourseTag.id)
    ).all()
    return [_view(session, user, tag) for tag in tags]


def create_tag(
    session: Session, user: Profile, payload: schemas.CourseTagCreate
) -> schemas.CourseTag:
    _check_role(user)
    _name_free(session, user, payload.name)
    tag = CourseTag(user_id=user.id, name=payload.name, color=payload.color)
    session.add(tag)
    session.flush()
    return _view(session, user, tag)


def update_tag(
    session: Session, user: Profile, tag_id: uuid.UUID, payload: schemas.CourseTagUpdate
) -> schemas.CourseTag:
    tag = _own_tag(session, user, tag_id)
    if payload.name is not None:
        _name_free(session, user, payload.name, but=tag.id)
        tag.name = payload.name
    if payload.color is not None:
        tag.color = payload.color
    session.flush()
    return _view(session, user, tag)


def delete_tag(session: Session, user: Profile, tag_id: uuid.UUID) -> None:
    session.delete(_own_tag(session, user, tag_id))
    session.flush()


def tag_course(
    session: Session, user: Profile, tag_id: uuid.UUID, course_id: uuid.UUID
) -> None:
    tag = _own_tag(session, user, tag_id)
    visible_course(session, user, course_id)
    session.execute(
        insert(CourseTagLink)
        .values(tag_id=tag.id, course_id=course_id)
        .on_conflict_do_nothing()
    )


def untag_course(
    session: Session, user: Profile, tag_id: uuid.UUID, course_id: uuid.UUID
) -> None:
    tag = _own_tag(session, user, tag_id)
    visible_course(session, user, course_id)
    session.execute(
        delete(CourseTagLink).where(
            CourseTagLink.tag_id == tag.id, CourseTagLink.course_id == course_id
        )
    )
