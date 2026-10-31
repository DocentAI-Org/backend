import uuid

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import StudentUser
from app.schemas.course_tests import (
    Phase,
    StudentTest,
    StudentTestPhase,
    TestSubmission,
    TestSubmitted,
)
from app.services import course_tests, courses

router = APIRouter(prefix="/courses/{course_id}/test", tags=["student: pre/post-test"])


@router.get(
    "",
    response_model=list[StudentTestPhase],
    responses=error_responses(403, 404),
    summary="The pre-test and post-test: status and whether I have done them",
)
def list_phases(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> list[StudentTestPhase]:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return course_tests.student_phases(session, enrolment)


@router.get(
    "/{phase}",
    response_model=StudentTest,
    responses=error_responses(403, 404, 409),
    description="The questions, without the right option; empty once done. "
    "409 `test_not_open` if the phase is not open and not done.",
)
def read_phase(
    course_id: uuid.UUID, phase: Phase, student: StudentUser, session: DbSession
) -> StudentTest:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return course_tests.student_test(session, enrolment, phase)


@router.post(
    "/{phase}",
    status_code=201,
    response_model=TestSubmitted,
    responses=error_responses(403, 404, 409, 422),
    summary="Submit my answers, once",
    description=(
        "One answer per question. Nothing about right or wrong is returned. 409 "
        "`test_already_done`, `test_not_open` or `consent_required`."
    ),
)
def submit_phase(
    course_id: uuid.UUID,
    phase: Phase,
    payload: TestSubmission,
    student: StudentUser,
    session: DbSession,
) -> TestSubmitted:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return course_tests.submit(session, get_settings(), enrolment, phase, payload)
