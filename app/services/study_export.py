"""Study data export (P5, specs/011): consenting students only, pseudonymous ids, no
free text, as a ZIP of CSV files."""

import csv
import hashlib
import hmac
import io
import uuid
import zipfile
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    ConsentEvent,
    Conversation,
    Enrolment,
    ExerciseSubmission,
    InteractionLog,
    Message,
    Quiz,
    QuizItem,
    TestAnswer,
    TestAttempt,
    TestQuestion,
    Topic,
)
from app.services.interactions import student_ref

README = """# DocentAI study export

Pseudonymised data of the students whose latest consent is "given" (specs/011).
Each student is a `study_ref`, stable across exports. No names, emails, account ids
or free text.
Dates are UTC (ISO 8601). Booleans are `true`/`false`; empty means none.

- `students.csv`: one row per consenting student and course: `joined_at`,
  `consent_version`.
- `topics.csv`: the course topics; `topic_id` joins the other files.
- `messages.csv`: one row per chat message: `author` (student, tutor), `kind`,
  `hint_number`, `request_solution`.
- `exercises.csv`: one row per exercise: `verdict`, `error_type` (taxonomy code), topic.
- `quiz_items.csv`: one row per quiz question shown: `difficulty` (1-3), `correct`
  (empty if not answered).
- `tests.csv`: one row per pre/post-test answer: `phase` (pre, post), topic, `correct`.
- `interactions.csv`: one row per model call (P2): tokens, `latency_ms`,
  `estimated_cost_usd`, `outcome`.
"""


def study_ref(settings: Settings, student_id: uuid.UUID) -> str:
    return hmac.new(
        settings.study_export_secret.encode(), str(student_id).encode(), hashlib.sha256
    ).hexdigest()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([_cell(value) for value in row] for row in rows)
    return out.getvalue()


def consenting_students(session: Session) -> set[uuid.UUID]:
    """Students whose latest consent event is a give, whatever its version."""
    latest = session.execute(
        select(ConsentEvent.student_id, ConsentEvent.action)
        .ext(distinct_on(ConsentEvent.student_id))
        .order_by(
            ConsentEvent.student_id,
            ConsentEvent.created_at.desc(),
            ConsentEvent.id.desc(),
        )
    ).all()
    return {student_id for student_id, action in latest if action == "given"}


def _consent_versions(session: Session, students: set[uuid.UUID]) -> dict:
    rows = session.execute(
        select(ConsentEvent.student_id, ConsentEvent.version)
        .where(ConsentEvent.student_id.in_(students))
        .ext(distinct_on(ConsentEvent.student_id))
        .order_by(
            ConsentEvent.student_id,
            ConsentEvent.created_at.desc(),
            ConsentEvent.id.desc(),
        )
    ).all()
    return dict(rows)


def build(
    session: Session, settings: Settings, course_id: uuid.UUID | None = None
) -> bytes:
    students = consenting_students(session)
    ref = {student: study_ref(settings, student) for student in students}
    by_log_ref = {student_ref(settings, s): r for s, r in ref.items()}

    def in_scope(column: Any) -> list[Any]:
        return [column == course_id] if course_id else []

    enrolments = session.execute(
        select(Enrolment.student_id, Enrolment.course_id, Enrolment.joined_at)
        .where(Enrolment.student_id.in_(students), *in_scope(Enrolment.course_id))
        .order_by(Enrolment.course_id, Enrolment.joined_at)
    ).all()
    versions = _consent_versions(session, students)
    topics = session.execute(
        select(Topic.course_id, Topic.id, Topic.name)
        .where(*in_scope(Topic.course_id))
        .order_by(Topic.course_id, Topic.position)
    ).all()
    messages = session.execute(
        select(
            Conversation.student_id,
            Conversation.course_id,
            Message.conversation_id,
            Message.author,
            Message.kind,
            Message.hint_number,
            Message.request_solution,
            Message.created_at,
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.student_id.in_(students), *in_scope(Conversation.course_id))
        .order_by(Message.created_at, Message.id)
    ).all()
    exercises = session.execute(
        select(
            ExerciseSubmission.student_id,
            ExerciseSubmission.course_id,
            ExerciseSubmission.id,
            ExerciseSubmission.verdict,
            ExerciseSubmission.error_type,
            ExerciseSubmission.topic_id,
            ExerciseSubmission.topic_name,
            ExerciseSubmission.created_at,
        )
        .where(
            ExerciseSubmission.student_id.in_(students),
            *in_scope(ExerciseSubmission.course_id),
        )
        .order_by(ExerciseSubmission.created_at, ExerciseSubmission.id)
    ).all()
    quiz_items = session.execute(
        select(
            Quiz.student_id,
            Quiz.course_id,
            QuizItem.quiz_id,
            QuizItem.position,
            QuizItem.topic_id,
            QuizItem.topic_name,
            QuizItem.difficulty,
            QuizItem.correct,
            QuizItem.answered_at,
        )
        .join(Quiz, Quiz.id == QuizItem.quiz_id)
        .where(Quiz.student_id.in_(students), *in_scope(Quiz.course_id))
        .order_by(Quiz.started_at, QuizItem.quiz_id, QuizItem.position)
    ).all()
    test_answers = session.execute(
        select(
            TestAttempt.student_id,
            TestAttempt.course_id,
            TestAttempt.phase,
            TestAnswer.question_id,
            TestQuestion.topic_id,
            TestQuestion.topic_name,
            TestAnswer.correct,
            TestAttempt.submitted_at,
        )
        .join(TestAttempt, TestAttempt.id == TestAnswer.attempt_id)
        .join(TestQuestion, TestQuestion.id == TestAnswer.question_id)
        .where(TestAttempt.student_id.in_(students), *in_scope(TestAttempt.course_id))
        .order_by(TestAttempt.submitted_at, TestQuestion.position)
    ).all()
    interactions = session.execute(
        select(
            InteractionLog.student_ref,
            InteractionLog.course_id,
            InteractionLog.kind,
            InteractionLog.model,
            InteractionLog.input_tokens,
            InteractionLog.output_tokens,
            InteractionLog.latency_ms,
            InteractionLog.estimated_cost_usd,
            InteractionLog.outcome,
            InteractionLog.created_at,
        )
        .where(
            InteractionLog.student_ref.in_(by_log_ref),
            *in_scope(InteractionLog.course_id),
        )
        .order_by(InteractionLog.created_at, InteractionLog.id)
    ).all()

    files = {
        "students.csv": _csv(
            ["study_ref", "course_id", "joined_at", "consent_version"],
            ((ref[s], c, j, versions.get(s)) for s, c, j in enrolments),
        ),
        "topics.csv": _csv(["course_id", "topic_id", "topic_name"], topics),
        "messages.csv": _csv(
            [
                "study_ref",
                "course_id",
                "conversation_id",
                "author",
                "kind",
                "hint_number",
                "request_solution",
                "created_at",
            ],
            ((ref[s], *rest) for s, *rest in messages),
        ),
        "exercises.csv": _csv(
            [
                "study_ref",
                "course_id",
                "submission_id",
                "verdict",
                "error_type",
                "topic_id",
                "topic_name",
                "created_at",
            ],
            ((ref[s], *rest) for s, *rest in exercises),
        ),
        "quiz_items.csv": _csv(
            [
                "study_ref",
                "course_id",
                "quiz_id",
                "position",
                "topic_id",
                "topic_name",
                "difficulty",
                "correct",
                "answered_at",
            ],
            ((ref[s], *rest) for s, *rest in quiz_items),
        ),
        "tests.csv": _csv(
            [
                "study_ref",
                "course_id",
                "phase",
                "question_id",
                "topic_id",
                "topic_name",
                "correct",
                "submitted_at",
            ],
            ((ref[s], *rest) for s, *rest in test_answers),
        ),
        "interactions.csv": _csv(
            [
                "study_ref",
                "course_id",
                "kind",
                "model",
                "input_tokens",
                "output_tokens",
                "latency_ms",
                "estimated_cost_usd",
                "outcome",
                "created_at",
            ],
            # Only interactions whose ref is in by_log_ref are selected.
            ((by_log_ref[r], *rest) for r, *rest in interactions),  # type: ignore[index]
        ),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", README)
        for name, content in files.items():
            archive.writestr(name, content)
    return out.getvalue()
