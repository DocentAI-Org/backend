import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses, not_found
from app.core.pagination import Page, Pagination
from app.core.security import StudentUser
from app.llm.client import LLMClient, get_llm
from app.models import Conversation as ConversationRow
from app.models import Message
from app.schemas.chat import (
    Allowance,
    Conversation,
    MessageCreate,
    StudentConversationSummary,
    TutorExchange,
)
from app.services import ai_settings, allowance, courses, tutor

router = APIRouter(tags=["student: tutor chat"])

LLM = Annotated[LLMClient, Depends(get_llm)]
CONVERSATION = "/courses/{course_id}/conversations/{conversation_id}"


@router.get(
    "/allowance",
    response_model=Allowance,
    summary="Messages left today across all courses (the study's daily ceiling)",
)
def read_allowance(student: StudentUser, session: DbSession) -> Allowance:
    ceiling = ai_settings.study_ceiling(session, get_settings())
    return allowance.read_daily(session, get_settings(), ceiling.messages, student.id)


@router.get(
    "/courses/{course_id}/allowance",
    response_model=Allowance,
    responses=error_responses(403, 404),
    summary="Messages left in the course: its limit or the daily ceiling, the tighter",
)
def read_course_allowance(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> Allowance:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    settings = get_settings()
    ai = ai_settings.in_effect(session, settings, enrolment.course_id)
    return tutor.allowance_view(session, settings, ai, enrolment)


@router.post(
    "/courses/{course_id}/conversations",
    status_code=201,
    response_model=Conversation,
    responses=error_responses(403, 404),
)
def start_conversation(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> Conversation:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    conversation = ConversationRow(course_id=enrolment.course_id, student_id=student.id)
    session.add(conversation)
    session.flush()
    session.refresh(conversation)
    return tutor.conversation_view(session, conversation)


@router.get(
    "/courses/{course_id}/conversations",
    response_model=Page[StudentConversationSummary],
    responses=error_responses(403, 404),
)
def list_conversations(
    course_id: uuid.UUID, student: StudentUser, session: DbSession, page: Pagination
) -> Page[StudentConversationSummary]:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    items, total = tutor.list_conversations(session, enrolment, page.limit, page.offset)
    return Page[StudentConversationSummary](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    CONVERSATION, response_model=Conversation, responses=error_responses(403, 404)
)
def read_conversation(
    course_id: uuid.UUID,
    conversation_id: uuid.UUID,
    student: StudentUser,
    session: DbSession,
) -> Conversation:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    conversation = tutor.get_conversation(session, enrolment, conversation_id)
    return tutor.conversation_view(session, conversation)


@router.post(
    f"{CONVERSATION}/messages",
    status_code=201,
    response_model=TutorExchange,
    responses=error_responses(403, 404, 409, 422, 429, 503),
    summary="Ask the tutor; replies come only from validated material",
)
def send_message(
    course_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    student: StudentUser,
    session: DbSession,
    llm: LLM,
) -> TutorExchange:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    conversation = tutor.get_conversation(session, enrolment, conversation_id)
    return tutor.send_message(
        session,
        llm,
        get_settings(),
        enrolment,
        conversation,
        payload.text,
        payload.request_solution,
    )


@router.post(
    f"{CONVERSATION}/messages/{{message_id}}/retry",
    status_code=201,
    response_model=TutorExchange,
    responses=error_responses(403, 404, 409, 429, 503),
    summary="Retry a message whose reply failed",
)
def retry_message(
    course_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    student: StudentUser,
    session: DbSession,
    llm: LLM,
) -> TutorExchange:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    conversation = tutor.get_conversation(session, enrolment, conversation_id)
    # Locked so two concurrent retries cannot both pass the "failed" check.
    message = session.get(Message, message_id, with_for_update=True)
    if (
        message is None
        or message.conversation_id != conversation.id
        or message.author != "student"
        or message.status != "failed"
    ):
        raise not_found("Failed message")
    return tutor.send_message(
        session,
        llm,
        get_settings(),
        enrolment,
        conversation,
        message.text,
        message.request_solution,
        retry_of=message,
    )
