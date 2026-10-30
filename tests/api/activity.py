"""Seeds dated activity in the database for the dashboard and risk tests (spec 004)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
    Conversation,
    Enrolment,
    ExerciseSubmission,
    LearningRecordEntry,
    Message,
)
from tests.api.test_us2_courses import create_course

MISTAKES = {"incorrect", "partially_correct"}


def ago(days: float) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def course_with(client, db, teacher, *students, joined_days_ago: float = 0) -> dict:
    """A course the students joined `joined_days_ago` days ago, with no activity yet."""
    course = create_course(client, teacher)
    for student in students:
        response = client.post(
            "/v1/student/enrolments",
            headers=student.headers,
            json={"class_code": course["class_code"]},
        )
        assert response.status_code in (200, 201), response.text
        if joined_days_ago:
            backdate_enrolment(db, course["id"], student, joined_days_ago)
    return course


def backdate_enrolment(db, course_id: str, student, days: float) -> None:
    enrolment = db.scalars(
        select(Enrolment).where(
            Enrolment.course_id == uuid.UUID(course_id),
            Enrolment.student_id == student.id,
        )
    ).one()
    enrolment.joined_at = ago(days)
    db.commit()


def messages(db, course_id: str, student, days_ago: float, count: int = 1) -> None:
    conversation = Conversation(
        course_id=uuid.UUID(course_id),
        student_id=student.id,
        started_at=ago(days_ago),
        last_message_at=ago(days_ago),
    )
    db.add(conversation)
    db.flush()
    for _ in range(count):
        db.add(
            Message(
                conversation_id=conversation.id,
                author="student",
                kind="question",
                text="¿Cómo despejo la x?",
                created_at=ago(days_ago),
            )
        )
        db.add(
            Message(
                conversation_id=conversation.id,
                author="tutor",
                kind="answer",
                text="Pasa el 2 dividiendo.",
                created_at=ago(days_ago),
            )
        )
    db.commit()


def exercise(
    db,
    course_id: str,
    student,
    days_ago: float,
    verdict: str = "incorrect",
    error_type: str | None = "procedural",
    topic: dict | None = None,
    topic_name: str | None = None,
    is_stub: bool = False,
) -> None:
    """One submission; a mistake with a type also writes its learning-record entry."""
    topic_id = uuid.UUID(topic["id"]) if topic else None
    name = topic["name"] if topic else topic_name
    has_type = verdict in MISTAKES and error_type is not None
    submission = ExerciseSubmission(
        course_id=uuid.UUID(course_id),
        student_id=student.id,
        problem_statement="2(x - 3) = 4x + 2",
        worked_answer="2x - 3 = 4x + 2",
        verdict=verdict,
        error_type=error_type if has_type else None,
        topic_id=topic_id if has_type else None,
        topic_name=name if has_type else None,
        explanation="El 2 multiplica a cada término.",
        explanation_kind="answer" if verdict != "not_assessed" else "no_source",
        saved_to_record=has_type,
        is_stub=is_stub,
        created_at=ago(days_ago),
    )
    db.add(submission)
    db.flush()
    if has_type:
        db.add(
            LearningRecordEntry(
                course_id=submission.course_id,
                student_id=student.id,
                submission_id=submission.id,
                error_type=error_type,
                topic_id=topic_id,
                topic_name=name,
                created_at=ago(days_ago),
            )
        )
    db.commit()


def dashboard(client, teacher, course_id: str, period: str | None = None):
    params = {"period": period} if period else {}
    return client.get(
        f"/v1/teacher/courses/{course_id}/dashboard",
        headers=teacher.headers,
        params=params,
    )


def risk_of(client, teacher, course_id: str, student):
    return client.get(
        f"/v1/teacher/courses/{course_id}/students/{student.id}/risk",
        headers=teacher.headers,
    )
