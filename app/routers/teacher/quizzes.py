import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Pagination
from app.core.security import TeacherUser
from app.llm.client import LLMClient, get_llm
from app.schemas.quizzes import (
    GeneratedQuestions,
    GenerateQuestions,
    QuestionPage,
    QuestionStatus,
    QuestionUpdate,
    TeacherQuestion,
)
from app.services import courses, quiz_questions, topics

router = APIRouter(prefix="/courses/{course_id}", tags=["teacher: quiz questions"])


@router.post(
    "/topics/{topic_id}/questions/generate",
    status_code=201,
    response_model=GeneratedQuestions,
    responses=error_responses(404, 422, 503),
    summary="Draft quiz questions for a topic with the AI",
    description=(
        "Multiple-choice drafts from the topic's confirmed material (or, without any, "
        "the material closest to its name), each citing its source. They are stored "
        "as `pending`: students only see approved questions. Unusable drafts are "
        "dropped; `kind: no_source` when none is usable. Logged with its cost; not "
        "charged to any student."
    ),
)
def generate_questions(
    course_id: uuid.UUID,
    topic_id: uuid.UUID,
    payload: GenerateQuestions,
    teacher: TeacherUser,
    session: DbSession,
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> GeneratedQuestions:
    course = courses.get_owned_course(session, course_id, teacher)
    topic = topics.get_topic(session, course, topic_id)
    return quiz_questions.generate(
        session, llm, get_settings(), course, topic, payload.count
    )


@router.get(
    "/questions", response_model=QuestionPage, responses=error_responses(404, 422)
)
def list_questions(
    course_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    page: Pagination,
    status: Annotated[QuestionStatus | None, Query()] = None,
    topic_id: Annotated[uuid.UUID | None, Query()] = None,
) -> QuestionPage:
    course = courses.get_owned_course(session, course_id, teacher)
    return quiz_questions.list_questions(
        session, course, status, topic_id, page.limit, page.offset
    )


@router.patch(
    "/questions/{question_id}",
    response_model=TeacherQuestion,
    responses=error_responses(404, 422),
    summary="Edit, approve or reject a question",
    description=(
        "Any of the content fields and/or `status`. Changing the content of an AI "
        "draft marks it `edited`. Quizzes already started keep the version the "
        "student saw."
    ),
)
def update_question(
    course_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: QuestionUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> TeacherQuestion:
    course = courses.get_owned_course(session, course_id, teacher)
    question = quiz_questions.get_question(session, course, question_id)
    return quiz_questions.update_question(session, teacher.id, question, payload)
