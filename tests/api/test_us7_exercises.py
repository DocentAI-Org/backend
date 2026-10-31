"""US7 — exercise submission with real feedback and learning record (S4, spec 003)."""

from sqlalchemy import select

from app.core.config import get_settings
from app.models import InteractionLog
from tests.api.helpers import classroom
from tests.api.test_us6_topics import create_topic

EXERCISE = {
    "problem_statement": "Quita los paréntesis y despeja la incógnita: "
    "2(x - 3) = 4x + 2",
    "worked_answer": "2x - 3 = 4x + 2\n-2x = 5\nx = -5/2",
}
UNCOVERED = {
    "problem_statement": "¿Quién ganó el mundial de fútbol de 2010?",
    "worked_answer": "España",
}
MISTAKE = {
    "verdict": "incorrect",
    "mistake_location": "Paso 1: 2(x - 3) se ha escrito como 2x - 3",
    "error_type": "procedural",
    "topic": "T1",
    "explanation": "Al quitar el paréntesis, el 2 multiplica a cada término: 2x - 6.",
    "cited": ["F1"],
}


def submit(client, student, course_id: str, payload: dict | None = None):
    return client.post(
        f"/v1/student/courses/{course_id}/submissions",
        headers=student.headers,
        json=payload or EXERCISE,
    )


def record_of(client, student, course_id: str) -> dict:
    return client.get(
        f"/v1/student/courses/{course_id}/learning-record", headers=student.headers
    ).json()


def log_of(db, course_id: str) -> InteractionLog:
    return db.scalars(
        select(InteractionLog).where(InteractionLog.course_id == course_id)
    ).one()


def test_mistake_gets_grounded_feedback_and_a_learning_record_entry(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    create_topic(client, teacher, room.course_id, "Paréntesis")
    llm.reply = MISTAKE

    response = submit(client, student, room.course_id)

    assert response.status_code == 201, response.text
    feedback = response.json()
    assert feedback["is_stub"] is False
    assert feedback["verdict"] == "incorrect"
    assert feedback["mistake_location"] == MISTAKE["mistake_location"]
    assert feedback["error_type"] == "procedural"
    assert feedback["topic_name"] == "Paréntesis"
    assert feedback["explanation"] == MISTAKE["explanation"]
    assert feedback["explanation_kind"] == "answer"
    assert [c["document_name"] for c in feedback["citations"]] == ["ecuaciones.md"]
    assert feedback["saved_to_record"] is True

    entry = record_of(client, student, room.course_id)["items"][0]
    assert entry["submission_id"] == feedback["id"]
    assert (entry["error_type"], entry["topic_name"]) == ("procedural", "Paréntesis")

    log = log_of(db, room.course_id)
    assert (log.kind, log.outcome, log.model) == ("exercise", "incorrect", "fake-model")
    assert log.input_tokens > 0


def test_the_model_sees_material_topics_and_taxonomy_but_no_personal_data(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    create_topic(client, teacher, room.course_id, "Paréntesis")
    llm.reply = MISTAKE

    submit(client, student, room.course_id)

    system, messages = llm.chat_calls[-1]
    sent = system + "".join(m["content"] for m in messages)
    assert "Quitar paréntesis" in sent
    assert '<tema id="T1">Paréntesis</tema>' in sent
    assert "procedural" in sent and "comprehension" in sent
    assert EXERCISE["worked_answer"] in sent
    for personal in (student.id, student.display_name, "Lucas"):
        assert str(personal) not in sent


def test_correct_answer_has_no_error_type_and_nothing_is_recorded(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    create_topic(client, teacher, room.course_id, "Paréntesis")
    llm.reply = {
        **MISTAKE,
        "verdict": "correct",
        "mistake_location": None,
        "error_type": None,
        "explanation": "Correcto: has quitado bien el paréntesis.",
    }

    feedback = submit(client, student, room.course_id).json()

    assert feedback["verdict"] == "correct"
    # The topic counts toward progress (spec 007), but nothing goes to the record.
    assert feedback["topic_name"] == "Paréntesis"
    assert feedback["error_type"] is None
    assert feedback["mistake_location"] is None
    assert feedback["saved_to_record"] is False
    assert record_of(client, student, room.course_id)["total"] == 0
    assert log_of(db, room.course_id).outcome == "correct"


def test_uncovered_exercise_is_not_assessed_and_the_model_is_not_asked(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)

    feedback = submit(client, student, room.course_id, UNCOVERED).json()

    assert feedback["verdict"] == "not_assessed"
    assert feedback["explanation_kind"] == "no_source"
    assert feedback["citations"] == []
    assert feedback["error_type"] is None
    assert feedback["saved_to_record"] is False
    assert llm.chat_calls == []


def test_hints_only_courses_ask_for_feedback_without_the_full_solution(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    client.put(
        f"/v1/teacher/courses/{room.course_id}/tutor-settings",
        headers=teacher.headers,
        json={"level": "basic", "tone": "friendly", "solution_policy": "hints_only"},
    )
    llm.reply = MISTAKE

    submit(client, student, room.course_id)

    system, _ = llm.chat_calls[-1]
    assert "no escribas la solución completa" in system.lower()


def test_unfounded_model_reply_is_stored_as_not_assessed(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    llm.reply = {**MISTAKE, "cited": ["F9"]}

    feedback = submit(client, student, room.course_id).json()

    assert feedback["verdict"] == "not_assessed"
    assert feedback["explanation_kind"] == "no_source"
    assert feedback["citations"] == []
    assert feedback["saved_to_record"] is False


def test_provider_failure_returns_503_and_keeps_the_allowance(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    llm.fail_chat = True

    response = submit(client, student, room.course_id)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "tutor_unavailable"
    listed = client.get(
        f"/v1/student/courses/{room.course_id}/submissions", headers=student.headers
    ).json()
    assert listed["total"] == 0
    allowance = client.get("/v1/student/allowance", headers=student.headers).json()
    assert allowance["used"] == 0
    assert log_of(db, room.course_id).outcome == "error"


def test_unknown_error_type_keeps_feedback_but_skips_the_record(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    llm.reply = {**MISTAKE, "error_type": "typo"}

    feedback = submit(client, student, room.course_id).json()

    assert feedback["verdict"] == "incorrect"
    assert feedback["error_type"] is None
    assert feedback["explanation"] == MISTAKE["explanation"]
    assert feedback["saved_to_record"] is False
    assert record_of(client, student, room.course_id)["total"] == 0
    assert log_of(db, room.course_id).outcome == "unclassified"


def test_unknown_topic_is_dropped(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    create_topic(client, teacher, room.course_id, "Paréntesis")
    llm.reply = {**MISTAKE, "topic": "T7"}

    feedback = submit(client, student, room.course_id).json()

    assert feedback["topic_name"] is None
    entry = record_of(client, student, room.course_id)["items"][0]
    assert entry["topic_id"] is None and entry["topic_name"] is None


def test_submission_counts_toward_the_allowance(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    llm.reply = MISTAKE

    submit(client, student, room.course_id)

    allowance = client.get("/v1/student/allowance", headers=student.headers).json()
    assert allowance["used"] == 1


def test_submission_requires_disclosure_and_valid_input(
    client, teacher, student
) -> None:
    room = classroom(client, teacher, student, acknowledge=False)
    blocked = submit(client, student, room.course_id)
    assert blocked.json()["error"]["code"] == "disclosure_not_acknowledged"

    client.post(
        f"/v1/student/courses/{room.course_id}/disclosure", headers=student.headers
    )
    empty = submit(client, student, room.course_id, {**EXERCISE, "worked_answer": ""})
    assert empty.status_code == 422


def test_deleted_topic_keeps_its_name_in_the_learning_record(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    llm.reply = MISTAKE
    topic = create_topic(client, teacher, room.course_id, "Paréntesis").json()
    submit(client, student, room.course_id)

    client.delete(
        f"/v1/teacher/courses/{room.course_id}/topics/{topic['id']}",
        headers=teacher.headers,
    )

    entry = client.get(
        f"/v1/student/courses/{room.course_id}/learning-record",
        headers=student.headers,
    ).json()["items"][0]
    assert entry["topic_id"] is None
    assert entry["topic_name"] == "Paréntesis"
    assert entry["topic_deleted"] is True


def test_learning_record_is_visible_only_to_student_and_their_teacher(
    client, llm, teacher, other_teacher, student, other_student
) -> None:
    room = classroom(client, teacher, student)
    llm.reply = MISTAKE
    submit(client, student, room.course_id)
    teacher_path = (
        f"/v1/teacher/courses/{room.course_id}/students/{student.id}/learning-record"
    )

    as_teacher = client.get(teacher_path, headers=teacher.headers)
    assert as_teacher.status_code == 200
    assert as_teacher.json()["total"] == 1

    assert client.get(teacher_path, headers=other_teacher.headers).status_code == 404
    other_view = client.get(
        f"/v1/student/courses/{room.course_id}/learning-record",
        headers=other_student.headers,
    )
    assert other_view.status_code == 404


def test_student_lists_and_reads_own_submissions(
    client, llm, teacher, student, other_student
) -> None:
    room = classroom(client, teacher, student)
    llm.reply = MISTAKE
    created = submit(client, student, room.course_id).json()
    base = f"/v1/student/courses/{room.course_id}/submissions"

    listed = client.get(base, headers=student.headers).json()
    assert [s["id"] for s in listed["items"]] == [created["id"]]
    detail = client.get(f"{base}/{created['id']}", headers=student.headers)
    assert detail.json()["problem_statement"] == EXERCISE["problem_statement"]

    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    assert (
        client.get(f"{base}/{created['id']}", headers=other_student.headers).status_code
        == 404
    )


def test_submission_endpoint_is_no_longer_a_stub(client) -> None:
    operation = client.get("/openapi.json").json()["paths"][
        "/v1/student/courses/{course_id}/submissions"
    ]["post"]

    assert "x-stub" not in operation


def with_thresholds(monkeypatch, chat: str, exercises: str) -> None:
    monkeypatch.setenv("RETRIEVAL_MIN_SIMILARITY", chat)
    monkeypatch.setenv("RETRIEVAL_MIN_SIMILARITY_EXERCISES", exercises)
    get_settings.cache_clear()


def test_exercises_use_their_own_retrieval_threshold(
    client, llm, teacher, student, monkeypatch
) -> None:
    # Short statements sit below the chat threshold (spec 009 US3).
    room = classroom(client, teacher, student)
    llm.reply = MISTAKE
    with_thresholds(monkeypatch, chat="0.99", exercises="0.0")
    try:
        assessed = submit(client, student, room.course_id).json()
        with_thresholds(monkeypatch, chat="0.0", exercises="0.99")
        uncovered = submit(client, student, room.course_id).json()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    assert assessed["verdict"] == "incorrect"
    assert uncovered["verdict"] == "not_assessed"
