import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.security import StudentUser
from app.llm.client import LLMClient, get_llm
from app.schemas.exercises import (
    LearningRecordEntry,
    MistakeReview,
    StudentSubmission,
    SubmissionCreate,
)
from app.services import courses, exercises, reviews

router = APIRouter(prefix="/courses/{course_id}", tags=["student: exercises"])


@router.post(
    "/submissions",
    status_code=201,
    response_model=StudentSubmission,
    responses=error_responses(403, 404, 409, 422, 429, 503),
    summary="Submit a worked exercise and get feedback on the mistake",
    description=(
        "The tutor checks the answer against the course material: verdict, first "
        "mistake, error type (`GET /v1/error-types`), course topic and a cited "
        "explanation. Mistakes with a type go to the learning record. Exercises the "
        "material does not cover are `not_assessed`. Counts toward the daily "
        "allowance, except when the tutor is unavailable (503). `is_stub` is always "
        "false and will be removed."
    ),
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


@router.post(
    "/submissions/{submission_id}/review",
    status_code=201,
    response_model=MistakeReview,
    responses=error_responses(403, 404, 409, 429, 503),
    summary="A targeted review of a repeated mistake",
    description=(
        "Only for a submission with `repeated_mistake`, else 409 "
        "`no_repeated_mistake`. What is going wrong, a worked example and practice "
        "statements, grounded in the material. Created once (201) and counted toward "
        "the daily allowance; asking again returns the same review (200) for free."
    ),
)
def request_review(
    course_id: uuid.UUID,
    submission_id: uuid.UUID,
    student: StudentUser,
    session: DbSession,
    llm: Annotated[LLMClient, Depends(get_llm)],
    response: Response,
) -> MistakeReview:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    submission = exercises.get_submission(session, enrolment, submission_id)
    review, created = reviews.request_review(
        session, llm, get_settings(), enrolment, submission
    )
    if not created:
        response.status_code = 200
    return review


@router.get(
    "/submissions/{submission_id}/review",
    response_model=MistakeReview,
    responses=error_responses(403, 404),
)
def read_review(
    course_id: uuid.UUID,
    submission_id: uuid.UUID,
    student: StudentUser,
    session: DbSession,
) -> MistakeReview:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    submission = exercises.get_submission(session, enrolment, submission_id)
    return reviews.read_review(session, submission.id)


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
