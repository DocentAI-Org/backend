"""Erasure on request: a student and all linked to them (spec 017, AGENTS.md VI)."""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.integrations.auth_admin import AuthAdminClient
from app.models import (
    Conversation,
    Enrolment,
    ExerciseSubmission,
    InteractionLog,
    Message,
    Profile,
    Quiz,
    TestAttempt,
)
from app.schemas.admin import StudentErasure
from app.services.interactions import student_ref


def erase_student(
    session: Session,
    auth_admin: AuthAdminClient,
    settings: Settings,
    student_id: uuid.UUID,
) -> StudentErasure:
    profile = session.get(Profile, student_id)
    if profile is None:
        raise not_found("Student")
    if profile.role != "student":
        # A teacher's courses hold every student's work; erasing them is not this.
        raise ApiError(409, "not_a_student", "Only student accounts can be erased.")

    def owned(model) -> int:
        query = select(func.count()).select_from(model)
        return session.scalar(query.where(model.student_id == student_id)) or 0

    messages = (
        session.scalar(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.student_id == student_id)
        )
        or 0
    )
    counts = {
        "courses": owned(Enrolment),
        "conversations": owned(Conversation),
        "messages": messages,
        "exercise_submissions": owned(ExerciseSubmission),
        "quizzes": owned(Quiz),
        "test_attempts": owned(TestAttempt),
    }

    # The logs hold a keyed hash, not the account id, so nothing cascades to them.
    # They go first, in the request's transaction: if the auth call fails, they stay.
    logs = session.execute(
        delete(InteractionLog).where(
            InteractionLog.student_ref == student_ref(settings, student_id)
        )
    ).rowcount
    session.flush()
    session.expunge(profile)
    # Deleting auth.users cascades to the profile and every row that references it.
    auth_admin.delete_user(student_id)
    return StudentErasure(student_id=student_id, interaction_logs=logs, **counts)
