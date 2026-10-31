import uuid

from fastapi import APIRouter, Response

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import TeacherUser
from app.schemas.course_tests import (
    CopyQuizQuestion,
    CourseTest,
    Phase,
    PhaseUpdate,
    TestPhaseView,
    TestQuestion,
    TestQuestionCreate,
    TestQuestionUpdate,
    TestResults,
)
from app.services import course_tests, courses

router = APIRouter(prefix="/courses/{course_id}/test", tags=["teacher: pre/post-test"])


@router.get(
    "",
    response_model=CourseTest,
    responses=error_responses(404),
    summary="The course's pre/post-test: questions and phases",
)
def read_test(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> CourseTest:
    course = courses.get_owned_course(session, course_id, teacher)
    return course_tests.course_test(session, course)


@router.post(
    "/questions",
    status_code=201,
    response_model=TestQuestion,
    responses=error_responses(404, 409, 422),
    description="409 `test_locked` once the pre-test has been opened.",
)
def add_question(
    course_id: uuid.UUID,
    payload: TestQuestionCreate,
    teacher: TeacherUser,
    session: DbSession,
) -> TestQuestion:
    course = courses.get_owned_course(session, course_id, teacher)
    return course_tests.add_question(session, course, payload)


@router.post(
    "/questions/from-quiz",
    status_code=201,
    response_model=TestQuestion,
    responses=error_responses(404, 409, 422),
    summary="Copy an approved quiz question into the test",
)
def copy_quiz_question(
    course_id: uuid.UUID,
    payload: CopyQuizQuestion,
    teacher: TeacherUser,
    session: DbSession,
) -> TestQuestion:
    course = courses.get_owned_course(session, course_id, teacher)
    return course_tests.copy_quiz_question(session, course, payload.question_id)


@router.patch(
    "/questions/{question_id}",
    response_model=TestQuestion,
    responses=error_responses(404, 409, 422),
)
def update_question(
    course_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: TestQuestionUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> TestQuestion:
    course = courses.get_owned_course(session, course_id, teacher)
    question = course_tests.get_question(session, course, question_id)
    return course_tests.update_question(session, course, question, payload)


@router.delete(
    "/questions/{question_id}", status_code=204, responses=error_responses(404, 409)
)
def delete_question(
    course_id: uuid.UUID,
    question_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    question = course_tests.get_question(session, course, question_id)
    course_tests.delete_question(session, course, question)
    return Response(status_code=204)


@router.put(
    "/phases/{phase}",
    response_model=TestPhaseView,
    responses=error_responses(404, 409, 422),
    summary="Open or close the pre-test or the post-test",
    description=(
        "409 `test_empty` without questions. Opening the pre-test freezes the "
        "questions. A closed phase can be opened again; answers given stay."
    ),
)
def set_phase(
    course_id: uuid.UUID,
    phase: Phase,
    payload: PhaseUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> TestPhaseView:
    course = courses.get_owned_course(session, course_id, teacher)
    return course_tests.set_phase(session, course, phase, payload.status)


@router.get(
    "/results",
    response_model=TestResults,
    responses=error_responses(404),
    summary="Scores by student, phase and topic, and course averages",
)
def read_results(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> TestResults:
    course = courses.get_owned_course(session, course_id, teacher)
    return course_tests.results(session, course)
