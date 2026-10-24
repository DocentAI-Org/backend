"""Teacher review of conversations and feedback, and corrections (T4, T6)."""

import uuid
from datetime import datetime

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.models import (
    Conversation,
    Course,
    ExerciseSubmission,
    Message,
    Profile,
    TeacherFlag,
)
from app.schemas import review as schemas
from app.services import exercises, tutor


def flag_view(flag: TeacherFlag | None) -> schemas.TeacherFlag | None:
    if flag is None:
        return None
    return schemas.TeacherFlag(
        id=flag.id,
        category=flag.category,  # type: ignore[arg-type]
        correction=flag.correction,
        author_name=flag.author.display_name if flag.author else None,
        created_at=flag.created_at,
        updated_at=flag.updated_at,
    )


def teacher_message_view(message: Message) -> schemas.TeacherMessage:
    return schemas.TeacherMessage(
        **tutor.message_view(message).model_dump(), flag=flag_view(message.flag)
    )


def submission_view(submission: ExerciseSubmission) -> schemas.TeacherSubmission:
    return schemas.TeacherSubmission(
        **exercises.submission_view(submission).model_dump(),
        student_id=submission.student_id,
        student_name=submission.student.display_name,
        flag=flag_view(submission.flag),
    )


def _has_no_source():
    return exists().where(
        Message.conversation_id == Conversation.id, Message.kind == "no_source"
    )


def _has_correction():
    return exists().where(
        Message.conversation_id == Conversation.id,
        TeacherFlag.message_id == Message.id,
    )


def _summary_query(course: Course) -> Select:
    message_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    return select(
        Conversation,
        message_count.label("count"),
        _has_no_source().label("no_source"),
        _has_correction().label("corrected"),
    ).where(Conversation.course_id == course.id)


def _summary(row) -> schemas.ConversationSummary:
    conversation, count, no_source, corrected = row
    return schemas.ConversationSummary(
        id=conversation.id,
        student_id=conversation.student_id,
        student_name=conversation.student.display_name,
        started_at=conversation.started_at,
        last_message_at=conversation.last_message_at,
        message_count=count,
        has_no_source=no_source,
        has_correction=corrected,
    )


def list_conversations(
    session: Session,
    course: Course,
    limit: int,
    offset: int,
    student_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    has_no_source: bool | None = None,
    has_correction: bool | None = None,
) -> tuple[list[schemas.ConversationSummary], int]:
    query = _summary_query(course)
    if student_id:
        query = query.where(Conversation.student_id == student_id)
    if created_from:
        query = query.where(Conversation.last_message_at >= created_from)
    if created_to:
        query = query.where(Conversation.started_at <= created_to)
    if has_no_source is not None:
        condition = _has_no_source()
        query = query.where(condition if has_no_source else ~condition)
    if has_correction is not None:
        condition = _has_correction()
        query = query.where(condition if has_correction else ~condition)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Conversation.last_message_at.desc(), Conversation.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [_summary(r) for r in rows], total


def read_conversation(
    session: Session, course: Course, conversation_id: uuid.UUID
) -> schemas.TeacherConversation:
    row = session.execute(
        _summary_query(course).where(Conversation.id == conversation_id)
    ).one_or_none()
    if row is None:
        raise not_found("Conversation")
    summary = _summary(row)
    messages = tutor.conversation_messages(session, conversation_id)
    return schemas.TeacherConversation(
        **summary.model_dump(), messages=[teacher_message_view(m) for m in messages]
    )


def get_course_submission(
    session: Session, course: Course, submission_id: uuid.UUID
) -> ExerciseSubmission:
    submission = session.get(ExerciseSubmission, submission_id)
    if submission is None or submission.course_id != course.id:
        raise not_found("Submission")
    return submission


def get_course_message(
    session: Session, course: Course, message_id: uuid.UUID
) -> Message:
    message = session.get(Message, message_id)
    if message is None:
        raise not_found("Message")
    conversation = session.get(Conversation, message.conversation_id)
    if conversation is None or conversation.course_id != course.id:
        raise not_found("Message")
    if message.author != "tutor":
        raise ApiError(
            400, "not_a_tutor_message", "Only tutor messages can be flagged."
        )
    return message


def upsert_flag(
    session: Session,
    course: Course,
    teacher: Profile,
    payload: schemas.FlagUpsert,
    *,
    message: Message | None = None,
    submission: ExerciseSubmission | None = None,
) -> schemas.TeacherFlag:
    target = message if message is not None else submission
    assert target is not None
    flag = target.flag
    if flag is None:
        flag = TeacherFlag(
            course_id=course.id,
            message_id=message.id if message else None,
            submission_id=submission.id if submission else None,
        )
        session.add(flag)
    flag.category = payload.category
    flag.correction = payload.correction
    flag.author_id = teacher.id
    session.flush()
    session.refresh(flag)
    view = flag_view(flag)
    assert view is not None
    return view


def delete_flag(session: Session, flag: TeacherFlag | None) -> None:
    if flag is None:
        raise not_found("Flag")
    session.delete(flag)
    session.flush()


def evaluation_set(
    session: Session, limit: int, offset: int
) -> tuple[list[schemas.EvaluationItem], int]:
    """Flags and corrections for the evaluation set (§4.4); no student data."""
    total = session.scalar(select(func.count(TeacherFlag.id))) or 0
    flags = session.scalars(
        select(TeacherFlag)
        .order_by(TeacherFlag.created_at.desc(), TeacherFlag.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = []
    for flag in flags:
        if flag.message_id:
            message = session.get(Message, flag.message_id)
            assert message is not None
            question = session.scalar(
                select(Message.text)
                .where(
                    Message.conversation_id == message.conversation_id,
                    Message.author == "student",
                    Message.created_at <= message.created_at,
                )
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            original, citations = message.text, message.citations
        else:
            submission = session.get(ExerciseSubmission, flag.submission_id)
            assert submission is not None
            question = f"{submission.problem_statement}\n\n{submission.worked_answer}"
            original, citations = submission.explanation, submission.citations
        items.append(
            schemas.EvaluationItem(
                flag_id=flag.id,
                course_id=flag.course_id,
                category=flag.category,  # type: ignore[arg-type]
                correction=flag.correction,
                question=question or "",
                original_answer=original,
                citations=[tutor.citation_view(c) for c in citations],
                created_at=flag.created_at,
            )
        )
    return items, total


def list_flags(
    session: Session, course: Course, limit: int, offset: int
) -> tuple[list[schemas.CourseFlag], int]:
    query = select(TeacherFlag).where(TeacherFlag.course_id == course.id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    flags = session.scalars(
        query.order_by(TeacherFlag.created_at.desc(), TeacherFlag.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = []
    for flag in flags:
        if flag.message_id:
            message = session.get(Message, flag.message_id)
            assert message is not None
            conversation = session.get(Conversation, message.conversation_id)
            assert conversation is not None
            student, original = conversation.student, message.text
            target = {
                "target": "message",
                "conversation_id": conversation.id,
                "message_id": message.id,
                "submission_id": None,
            }
        else:
            submission = session.get(ExerciseSubmission, flag.submission_id)
            assert submission is not None
            student, original = submission.student, submission.explanation
            target = {
                "target": "submission",
                "conversation_id": None,
                "message_id": None,
                "submission_id": submission.id,
            }
        view = flag_view(flag)
        assert view is not None
        items.append(
            schemas.CourseFlag(
                **view.model_dump(),
                student_id=student.id,
                student_name=student.display_name,
                original_text=original,
                **target,
            )
        )
    return items, total
