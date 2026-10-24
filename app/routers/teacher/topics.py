import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import TeacherUser
from app.schemas.topics import (
    Topic,
    TopicAssignment,
    TopicAssignmentCreate,
    TopicAssignmentUpdate,
    TopicCreate,
    TopicOrder,
    TopicUpdate,
    UnassignedDocument,
)
from app.services import courses, topics

router = APIRouter(prefix="/courses/{course_id}", tags=["teacher: topics"])


@router.get("/topics", response_model=list[Topic], responses=error_responses(404))
def list_topics(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> list[Topic]:
    course = courses.get_owned_course(session, course_id, teacher)
    return topics.list_topics(session, course)


@router.post(
    "/topics",
    status_code=201,
    response_model=Topic,
    responses=error_responses(404, 409, 422),
)
def create_topic(
    course_id: uuid.UUID, payload: TopicCreate, teacher: TeacherUser, session: DbSession
) -> Topic:
    course = courses.get_owned_course(session, course_id, teacher)
    topic = topics.create_topic(session, course, payload.name)
    return topics.topic_view(session, course, topic)


@router.put(
    "/topics/order", response_model=list[Topic], responses=error_responses(404, 422)
)
def reorder_topics(
    course_id: uuid.UUID, payload: TopicOrder, teacher: TeacherUser, session: DbSession
) -> list[Topic]:
    course = courses.get_owned_course(session, course_id, teacher)
    return topics.reorder(session, course, payload.topic_ids)


@router.patch(
    "/topics/{topic_id}",
    response_model=Topic,
    responses=error_responses(404, 409, 422),
)
def rename_topic(
    course_id: uuid.UUID,
    topic_id: uuid.UUID,
    payload: TopicUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> Topic:
    course = courses.get_owned_course(session, course_id, teacher)
    topic = topics.rename_topic(
        session, topics.get_topic(session, course, topic_id), payload.name
    )
    return topics.topic_view(session, course, topic)


@router.delete("/topics/{topic_id}", status_code=204, responses=error_responses(404))
def delete_topic(
    course_id: uuid.UUID, topic_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    topics.delete_topic(session, topics.get_topic(session, course, topic_id))
    return Response(status_code=204)


@router.get(
    "/topic-assignments",
    response_model=list[TopicAssignment],
    responses=error_responses(404),
)
def list_assignments(
    course_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    status: Annotated[Literal["suggested", "confirmed"] | None, Query()] = None,
) -> list[TopicAssignment]:
    course = courses.get_owned_course(session, course_id, teacher)
    return topics.list_assignments(session, course, status)


@router.post(
    "/topic-assignments",
    status_code=201,
    response_model=TopicAssignment,
    responses=error_responses(404, 409, 422),
)
def create_assignment(
    course_id: uuid.UUID,
    payload: TopicAssignmentCreate,
    teacher: TeacherUser,
    session: DbSession,
) -> TopicAssignment:
    course = courses.get_owned_course(session, course_id, teacher)
    return topics.create_assignment(session, course, teacher.id, payload)


@router.patch(
    "/topic-assignments/{assignment_id}",
    response_model=TopicAssignment,
    responses=error_responses(404, 422),
    summary="Confirm a suggested assignment, optionally changing its topic",
)
def confirm_assignment(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: TopicAssignmentUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> TopicAssignment:
    course = courses.get_owned_course(session, course_id, teacher)
    assignment = topics.get_assignment(session, course, assignment_id)
    return topics.confirm_assignment(
        session, course, teacher.id, assignment, payload.topic_id
    )


@router.delete(
    "/topic-assignments/{assignment_id}",
    status_code=204,
    responses=error_responses(404),
)
def delete_assignment(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    session.delete(topics.get_assignment(session, course, assignment_id))
    session.flush()
    return Response(status_code=204)


@router.get(
    "/unassigned-material",
    response_model=list[UnassignedDocument],
    responses=error_responses(404),
)
def unassigned_material(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> list[UnassignedDocument]:
    course = courses.get_owned_course(session, course_id, teacher)
    return topics.unassigned_material(session, course)
