import uuid

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.security import StudentUser
from app.schemas.quizzes import (
    AnswerResult,
    Quiz,
    QuizAnswer,
    QuizDetail,
    QuizStart,
    QuizTopic,
)
from app.services import courses, quizzes

router = APIRouter(prefix="/courses/{course_id}", tags=["student: quizzes"])


@router.post(
    "/quizzes",
    status_code=201,
    response_model=Quiz,
    responses=error_responses(403, 404, 409, 422),
    summary="Start an adaptive quiz",
    description=(
        "Over the teacher's approved questions, for one topic or all. 409 "
        "`no_questions` when there are none. Answering never calls the model and "
        "does not count toward the daily allowance."
    ),
)
def start_quiz(
    course_id: uuid.UUID, payload: QuizStart, student: StudentUser, session: DbSession
) -> Quiz:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return quizzes.start(session, get_settings(), enrolment, payload.topic_id)


@router.get(
    "/quiz-topics",
    response_model=list[QuizTopic],
    responses=error_responses(403, 404),
    summary="Topics a quiz can be about",
    description="Course topics with approved questions, in course order.",
)
def list_quiz_topics(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> list[QuizTopic]:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return quizzes.quiz_topics(session, enrolment)


@router.get("/quizzes", response_model=Page[Quiz], responses=error_responses(403, 404))
def list_quizzes(
    course_id: uuid.UUID, student: StudentUser, session: DbSession, page: Pagination
) -> Page[Quiz]:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    items, total = quizzes.list_quizzes(session, enrolment, page.limit, page.offset)
    return Page[Quiz](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/quizzes/{quiz_id}", response_model=QuizDetail, responses=error_responses(403, 404)
)
def read_quiz(
    course_id: uuid.UUID, quiz_id: uuid.UUID, student: StudentUser, session: DbSession
) -> QuizDetail:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return quizzes.quiz_detail(quizzes.get_quiz(session, enrolment, quiz_id))


@router.post(
    "/quizzes/{quiz_id}/answers",
    response_model=AnswerResult,
    responses=error_responses(403, 404, 409, 422),
    summary="Answer the current question",
    description=(
        "Immediate feedback: whether it was right, the correct option, the "
        "explanation and its sources, and the next question. `difficulty_change` "
        "says when and why the level moved. 409 `not_current_question` or "
        "`quiz_completed`."
    ),
)
def answer_question(
    course_id: uuid.UUID,
    quiz_id: uuid.UUID,
    payload: QuizAnswer,
    student: StudentUser,
    session: DbSession,
) -> AnswerResult:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    quiz = quizzes.get_quiz(session, enrolment, quiz_id)
    return quizzes.answer(session, get_settings(), enrolment, quiz, payload)
