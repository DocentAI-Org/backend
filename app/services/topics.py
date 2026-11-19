"""Course topics and their assignment to material (T9)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.models import Course, Document, Fragment, Topic, TopicAssignment
from app.schemas import topics as schemas


def _name_taken() -> ApiError:
    return ApiError(409, "topic_name_taken", "A topic with this name already exists.")


def get_topic(session: Session, course: Course, topic_id: uuid.UUID) -> Topic:
    topic = session.get(Topic, topic_id)
    if topic is None or topic.course_id != course.id:
        raise not_found("Topic")
    return topic


def _assignment_counts(session: Session, course: Course) -> dict[uuid.UUID, int]:
    rows = session.execute(
        select(TopicAssignment.topic_id, func.count(TopicAssignment.id))
        .where(TopicAssignment.course_id == course.id)
        .group_by(TopicAssignment.topic_id)
    ).all()
    return dict(rows)


def list_topics(session: Session, course: Course) -> list[schemas.Topic]:
    counts = _assignment_counts(session, course)
    rows = session.scalars(
        select(Topic)
        .where(Topic.course_id == course.id)
        .order_by(Topic.position, Topic.created_at)
    ).all()
    return [
        schemas.Topic(
            id=t.id,
            name=t.name,
            position=t.position,
            assignment_count=counts.get(t.id, 0),
        )
        for t in rows
    ]


def topic_view(session: Session, course: Course, topic: Topic) -> schemas.Topic:
    count = _assignment_counts(session, course).get(topic.id, 0)
    return schemas.Topic(
        id=topic.id, name=topic.name, position=topic.position, assignment_count=count
    )


def _flush_unique(session: Session) -> None:
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise _name_taken() from exc


def create_topic(session: Session, course: Course, name: str) -> Topic:
    position = (
        session.scalar(
            select(func.coalesce(func.max(Topic.position), 0)).where(
                Topic.course_id == course.id
            )
        )
        or 0
    ) + 1
    topic = Topic(course_id=course.id, name=name.strip(), position=position)
    session.add(topic)
    _flush_unique(session)
    session.refresh(topic)
    return topic


def rename_topic(session: Session, topic: Topic, name: str) -> Topic:
    topic.name = name.strip()
    _flush_unique(session)
    return topic


def reorder(
    session: Session, course: Course, topic_ids: list[uuid.UUID]
) -> list[schemas.Topic]:
    topics = {
        t.id: t
        for t in session.scalars(select(Topic).where(Topic.course_id == course.id))
    }
    if len(topic_ids) != len(set(topic_ids)) or set(topic_ids) != set(topics):
        raise ApiError(
            422,
            "validation_error",
            "topic_ids must list every topic of the course exactly once.",
        )
    for position, topic_id in enumerate(topic_ids, start=1):
        topics[topic_id].position = position
    session.flush()
    return list_topics(session, course)


def delete_topic(session: Session, topic: Topic) -> None:
    # Learning-record entries keep `topic_name`; their topic_id becomes NULL.
    session.delete(topic)
    session.flush()


def _assignment_view(assignment: TopicAssignment) -> schemas.TopicAssignment:
    return schemas.TopicAssignment(
        id=assignment.id,
        topic_id=assignment.topic_id,
        topic_name=assignment.topic.name,
        document_id=assignment.document_id,
        document_name=assignment.document.file_name,
        section=assignment.section,
        status=assignment.status,
    )


def list_assignments(
    session: Session, course: Course, status: str | None
) -> list[schemas.TopicAssignment]:
    query = select(TopicAssignment).where(TopicAssignment.course_id == course.id)
    if status:
        query = query.where(TopicAssignment.status == status)
    rows = session.scalars(query.order_by(TopicAssignment.created_at)).all()
    return [_assignment_view(a) for a in rows]


def get_assignment(
    session: Session, course: Course, assignment_id: uuid.UUID
) -> TopicAssignment:
    assignment = session.get(TopicAssignment, assignment_id)
    if assignment is None or assignment.course_id != course.id:
        raise not_found("Topic assignment")
    return assignment


def create_assignment(
    session: Session,
    course: Course,
    teacher_id: uuid.UUID,
    payload: schemas.TopicAssignmentCreate,
) -> schemas.TopicAssignment:
    topic = get_topic(session, course, payload.topic_id)
    document = session.get(Document, payload.document_id)
    if document is None or document.course_id != course.id:
        raise not_found("Document")
    assignment = TopicAssignment(
        course_id=course.id,
        topic_id=topic.id,
        document_id=document.id,
        section=payload.section,
        status="confirmed",
        confirmed_by=teacher_id,
        confirmed_at=datetime.now(UTC),
    )
    session.add(assignment)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise ApiError(
            409, "conflict", "This material is already assigned to the topic."
        ) from exc
    session.refresh(assignment)
    return _assignment_view(assignment)


def confirm_assignment(
    session: Session,
    course: Course,
    teacher_id: uuid.UUID,
    assignment: TopicAssignment,
    topic_id: uuid.UUID | None,
) -> schemas.TopicAssignment:
    if topic_id is not None:
        assignment.topic_id = get_topic(session, course, topic_id).id
    assignment.status = "confirmed"
    assignment.confirmed_by = teacher_id
    assignment.confirmed_at = datetime.now(UTC)
    session.flush()
    session.expire(assignment, ["topic"])
    return _assignment_view(assignment)


def unassigned_material(
    session: Session, course: Course
) -> list[schemas.UnassignedDocument]:
    documents = session.scalars(
        select(Document)
        .where(
            Document.course_id == course.id,
            Document.validation_status == "validated",
        )
        .order_by(Document.uploaded_at)
    ).all()
    confirmed = session.execute(
        select(TopicAssignment.document_id, TopicAssignment.section).where(
            TopicAssignment.course_id == course.id,
            TopicAssignment.status == "confirmed",
        )
    ).all()
    whole_documents = {doc_id for doc_id, section in confirmed if section is None}
    sections_done = {(doc_id, section) for doc_id, section in confirmed if section}
    result = []
    for document in documents:
        if document.id in whole_documents:
            continue
        sections = session.scalars(
            select(Fragment.section)
            .where(Fragment.document_id == document.id)
            .group_by(Fragment.section)
            .order_by(func.min(Fragment.position))
        ).all()
        pending = [s for s in sections if (document.id, s) not in sections_done]
        result.append(
            schemas.UnassignedDocument(
                document_id=document.id,
                document_name=document.file_name,
                sections=pending,
            )
        )
    return result
