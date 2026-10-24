"""US4 — every model interaction is logged with its cost (P2, FR-062, SC-004)."""

from sqlalchemy import select

from app.models import InteractionLog
from tests.api.helpers import (
    COVERED_QUESTION,
    UNCOVERED_QUESTION,
    ask,
    classroom,
    open_conversation,
)


def test_tutor_reply_writes_an_interaction_log(client, db, teacher, student) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)

    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    ask(client, student, room.course_id, conversation["id"], UNCOVERED_QUESTION)

    logs = db.scalars(
        select(InteractionLog)
        .where(InteractionLog.course_id == room.course_id)
        .order_by(InteractionLog.created_at)
    ).all()
    assert [log.outcome for log in logs] == ["answer", "no_source"]

    answered, uncovered = logs
    assert answered.kind == "chat"
    assert answered.question == COVERED_QUESTION
    assert answered.model == "fake-model"
    assert answered.input_tokens > 0
    assert answered.output_tokens == 20
    assert answered.latency_ms >= 0
    assert answered.retrieved_fragment_ids
    assert answered.answer

    assert uncovered.model is None
    assert uncovered.input_tokens == uncovered.output_tokens == 0

    for log in logs:
        assert log.student_ref != str(student.id)
        assert len(log.student_ref) == 64


def test_failed_call_is_logged_as_error(client, db, teacher, student, llm) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    llm.fail_chat = True

    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)

    log = db.scalars(
        select(InteractionLog).where(InteractionLog.course_id == room.course_id)
    ).one()
    assert log.outcome == "error"
    assert log.error_code == "tutor_unavailable"
