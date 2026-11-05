import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.pagination import Page, Pagination
from app.core.search import Search
from app.core.security import TeacherUser
from app.schemas.exercises import LearningRecordEntry, MistakeReview
from app.schemas.review import (
    ConversationSummary,
    CourseFlag,
    FlagUpsert,
    TeacherConversation,
    TeacherFlag,
    TeacherSubmission,
)
from app.services import courses, exercises, review, reviews

router = APIRouter(prefix="/courses/{course_id}", tags=["teacher: review"])

From = Annotated[datetime | None, Query(alias="from")]
To = Annotated[datetime | None, Query(alias="to")]


@router.get(
    "/conversations",
    response_model=Page[ConversationSummary],
    responses=error_responses(404),
)
def list_conversations(
    course_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    page: Pagination,
    student_id: Annotated[uuid.UUID | None, Query()] = None,
    created_from: From = None,
    created_to: To = None,
    has_no_source: Annotated[bool | None, Query()] = None,
    has_correction: Annotated[bool | None, Query()] = None,
    q: Search = None,
    sort: review.ConversationSort = "recent",
) -> Page[ConversationSummary]:
    course = courses.get_owned_course(session, course_id, teacher)
    items, total = review.list_conversations(
        session,
        course,
        page.limit,
        page.offset,
        student_id=student_id,
        created_from=created_from,
        created_to=created_to,
        has_no_source=has_no_source,
        has_correction=has_correction,
        q=q,
        sort=sort,
    )
    return Page[ConversationSummary](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=TeacherConversation,
    responses=error_responses(404),
)
def read_conversation(
    course_id: uuid.UUID,
    conversation_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> TeacherConversation:
    course = courses.get_owned_course(session, course_id, teacher)
    return review.read_conversation(session, course, conversation_id)


@router.get(
    "/submissions",
    response_model=Page[TeacherSubmission],
    responses=error_responses(404),
)
def list_submissions(
    course_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    page: Pagination,
    student_id: Annotated[uuid.UUID | None, Query()] = None,
    created_from: From = None,
    created_to: To = None,
    q: Search = None,
    sort: exercises.SubmissionSort = "recent",
) -> Page[TeacherSubmission]:
    course = courses.get_owned_course(session, course_id, teacher)
    rows, total = exercises.list_submissions(
        session,
        course.id,
        student_id,
        page.limit,
        page.offset,
        created_from=created_from,
        created_to=created_to,
        q=q,
        sort=sort,
    )
    return Page[TeacherSubmission](
        items=[review.submission_view(s) for s in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/submissions/{submission_id}",
    response_model=TeacherSubmission,
    responses=error_responses(404),
)
def read_submission(
    course_id: uuid.UUID,
    submission_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> TeacherSubmission:
    course = courses.get_owned_course(session, course_id, teacher)
    submission = review.get_course_submission(session, course, submission_id)
    return review.submission_view(submission)


@router.get(
    "/submissions/{submission_id}/review",
    response_model=MistakeReview,
    responses=error_responses(404),
    summary="The review the student got for a repeated mistake",
)
def read_review(
    course_id: uuid.UUID,
    submission_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> MistakeReview:
    course = courses.get_owned_course(session, course_id, teacher)
    submission = review.get_course_submission(session, course, submission_id)
    return reviews.read_review(session, submission.id)


@router.put(
    "/messages/{message_id}/flag",
    response_model=TeacherFlag,
    responses=error_responses(400, 404, 422),
    summary="Flag a tutor message and write the correction the student will see",
)
def flag_message(
    course_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: FlagUpsert,
    teacher: TeacherUser,
    session: DbSession,
) -> TeacherFlag:
    course = courses.get_owned_course(session, course_id, teacher)
    message = review.get_course_message(session, course, message_id)
    return review.upsert_flag(session, course, teacher, payload, message=message)


@router.delete(
    "/messages/{message_id}/flag", status_code=204, responses=error_responses(404)
)
def unflag_message(
    course_id: uuid.UUID,
    message_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    message = review.get_course_message(session, course, message_id)
    review.delete_flag(session, message.flag)
    return Response(status_code=204)


@router.put(
    "/submissions/{submission_id}/flag",
    response_model=TeacherFlag,
    responses=error_responses(404, 422),
)
def flag_submission(
    course_id: uuid.UUID,
    submission_id: uuid.UUID,
    payload: FlagUpsert,
    teacher: TeacherUser,
    session: DbSession,
) -> TeacherFlag:
    course = courses.get_owned_course(session, course_id, teacher)
    submission = review.get_course_submission(session, course, submission_id)
    return review.upsert_flag(session, course, teacher, payload, submission=submission)


@router.delete(
    "/submissions/{submission_id}/flag",
    status_code=204,
    responses=error_responses(404),
)
def unflag_submission(
    course_id: uuid.UUID,
    submission_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Response:
    course = courses.get_owned_course(session, course_id, teacher)
    submission = review.get_course_submission(session, course, submission_id)
    review.delete_flag(session, submission.flag)
    return Response(status_code=204)


@router.get(
    "/students/{student_id}/learning-record",
    response_model=Page[LearningRecordEntry],
    responses=error_responses(404),
)
def read_learning_record(
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    page: Pagination,
) -> Page[LearningRecordEntry]:
    course = courses.get_owned_course(session, course_id, teacher)
    courses.get_course_enrolment(session, course, student_id)
    items, total = exercises.learning_record(
        session, course.id, student_id, page.limit, page.offset
    )
    return Page[LearningRecordEntry](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    "/flags",
    response_model=Page[CourseFlag],
    responses=error_responses(404),
    summary="Every correction in the course, newest first",
)
def list_flags(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession, page: Pagination
) -> Page[CourseFlag]:
    course = courses.get_owned_course(session, course_id, teacher)
    items, total = review.list_flags(session, course, page.limit, page.offset)
    return Page[CourseFlag](
        items=items, total=total, limit=page.limit, offset=page.offset
    )
