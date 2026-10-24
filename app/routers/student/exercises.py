import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.security import StudentUser
from app.llm.client import LLMClient, get_llm
from app.schemas.exercises import (
    LearningRecordEntry,
    StudentSubmission,
    SubmissionCreate,
)
from app.services import courses, exercises

router = APIRouter(prefix="/courses/{course_id}", tags=["student: exercises"])


@router.post(
    "/submissions",
    status_code=201,
    response_model=StudentSubmission,
    responses=error_responses(403, 404, 409, 422, 429),
    summary="Submit a worked exercise (stub feedback in v1)",
    description=(
        "Stores the submission, its citations and a learning-record entry, and "
        "counts toward the daily allowance. The feedback content is a fixed "
        "placeholder until the error taxonomy is agreed (`is_stub: true`)."
    ),
    openapi_extra={"x-stub": True},
)
def submit_exercise(
    course_id: uuid.UUID,
    payload: SubmissionCreate,
    student: StudentUser,
    session: DbSession,
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> StudentSubmission:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return exercises.submit(
        session,
        llm,
        get_settings(),
        enrolment,
        payload.problem_statement,
        payload.worked_answer,
    )


@router.get(
    "/submissions",
    response_model=Page[StudentSubmission],
    responses=error_responses(403, 404),
)
def list_submissions(
    course_id: uuid.UUID, student: StudentUser, session: DbSession, page: Pagination
) -> Page[StudentSubmission]:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    rows, total = exercises.list_submissions(
        session, enrolment.course_id, student.id, page.limit, page.offset
    )
    return Page[StudentSubmission](
        items=[exercises.submission_view(s) for s in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/submissions/{submission_id}",
    response_model=StudentSubmission,
    responses=error_responses(403, 404),
)
def read_submission(
    course_id: uuid.UUID,
    submission_id: uuid.UUID,
    student: StudentUser,
    session: DbSession,
) -> StudentSubmission:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    submission = exercises.get_submission(session, enrolment, submission_id)
    return exercises.submission_view(submission)


@router.get(
    "/learning-record",
    response_model=Page[LearningRecordEntry],
    responses=error_responses(403, 404),
)
def read_learning_record(
    course_id: uuid.UUID, student: StudentUser, session: DbSession, page: Pagination
) -> Page[LearningRecordEntry]:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    items, total = exercises.learning_record(
        session, enrolment.course_id, student.id, page.limit, page.offset
    )
    return Page[LearningRecordEntry](
        items=items, total=total, limit=page.limit, offset=page.offset
    )
