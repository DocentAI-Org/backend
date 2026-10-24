"""US4 — student asks the tutor and gets a grounded, cited answer (S1, S2, S3)."""

from app.models import Message
from tests.api.helpers import (
    COVERED_QUESTION,
    UNCOVERED_QUESTION,
    ask,
    classroom,
    open_conversation,
)


def test_messages_require_the_ai_disclosure(client, teacher, student) -> None:
    room = classroom(client, teacher, student, acknowledge=False)
    conversation = open_conversation(client, student, room.course_id)

    blocked = ask(client, student, room.course_id, conversation["id"], "Hola")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "disclosure_not_acknowledged"

    acknowledged = client.post(
        f"/v1/student/courses/{room.course_id}/disclosure", headers=student.headers
    )
    assert acknowledged.json()["disclosure_acknowledged"] is True
    accepted = ask(client, student, room.course_id, conversation["id"], "Hola")
    assert accepted.status_code == 201


def test_covered_question_gets_answer_with_citations(
    client, teacher, student, llm
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)

    response = ask(
        client, student, room.course_id, conversation["id"], COVERED_QUESTION
    )

    assert response.status_code == 201, response.text
    exchange = response.json()
    assert exchange["student_message"]["kind"] == "question"
    assert exchange["student_message"]["counts_toward_limit"] is True
    tutor = exchange["tutor_message"]
    assert tutor["author"] == "tutor"
    assert tutor["kind"] == "answer"
    assert tutor["text"] == "Según el material, se resta 3 y se divide entre 2."
    assert len(tutor["citations"]) == 1
    citation = tutor["citations"][0]
    assert citation["document_name"] == "ecuaciones.md"
    assert citation["location_label"].startswith("§ ")
    assert citation["available"] is True
    assert citation["passage"]
    assert len(llm.chat_calls) == 1


def test_uncovered_question_returns_no_source_without_calling_the_model(
    client, teacher, student, llm
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)

    response = ask(
        client, student, room.course_id, conversation["id"], UNCOVERED_QUESTION
    )

    assert response.status_code == 201
    tutor = response.json()["tutor_message"]
    assert tutor["kind"] == "no_source"
    assert tutor["citations"] == []
    assert "no cubre" in tutor["text"]
    assert llm.chat_calls == []


def test_answer_citing_nothing_retrieved_becomes_no_source(
    client, teacher, student, llm
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    llm.reply = {"kind": "answer", "text": "Invento algo.", "cited": ["F9"]}

    response = ask(
        client, student, room.course_id, conversation["id"], COVERED_QUESTION
    )

    tutor = response.json()["tutor_message"]
    assert tutor["kind"] == "no_source"
    assert tutor["citations"] == []
    assert "Invento" not in tutor["text"]


def test_guided_mode_numbers_hints_and_policy_reaches_the_prompt(
    client, teacher, student, llm
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    llm.reply = {
        "kind": "hint",
        "text": "Piensa qué operación deshace la suma.",
        "cited": ["F1"],
    }

    first = ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    second = ask(client, student, room.course_id, conversation["id"], "No lo veo")

    assert first.json()["tutor_message"]["kind"] == "hint"
    assert first.json()["tutor_message"]["hint_number"] == 1
    assert second.json()["tutor_message"]["hint_number"] == 2
    system_prompt = llm.chat_calls[0][0]
    assert "da primero pistas" in system_prompt


def test_solution_request_follows_the_policy(client, teacher, student, llm) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)

    allowed = ask(
        client,
        student,
        room.course_id,
        conversation["id"],
        COVERED_QUESTION,
        request_solution=True,
    )
    assert allowed.status_code == 201
    assert "ha pedido expresamente la solución" in llm.chat_calls[-1][0]

    client.put(
        f"/v1/teacher/courses/{room.course_id}/tutor-settings",
        headers=teacher.headers,
        json={"level": "basic", "tone": "friendly", "solution_policy": "hints_only"},
    )
    blocked = ask(
        client,
        student,
        room.course_id,
        conversation["id"],
        COVERED_QUESTION,
        request_solution=True,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "solution_not_allowed"


def test_provider_failure_marks_message_failed_and_retry_works(
    client, db, teacher, student, llm
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    llm.fail_chat = True

    failed = ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)

    assert failed.status_code == 503
    error = failed.json()["error"]
    assert error["code"] == "tutor_unavailable"
    message_id = error["details"]["message_id"]
    stored = db.get(Message, message_id)
    assert stored.status == "failed"
    assert stored.counts_toward_limit is False
    allowance = client.get("/v1/student/allowance", headers=student.headers).json()
    assert allowance["used"] == 0

    llm.fail_chat = False
    retried = client.post(
        f"/v1/student/courses/{room.course_id}/conversations/{conversation['id']}"
        f"/messages/{message_id}/retry",
        headers=student.headers,
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["student_message"]["id"] == message_id
    assert retried.json()["student_message"]["status"] == "sent"
    assert retried.json()["tutor_message"]["kind"] == "answer"


def test_student_reads_conversations_and_teacher_settings(
    client, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)

    settings = client.get(
        f"/v1/student/courses/{room.course_id}/tutor-settings", headers=student.headers
    ).json()
    assert settings == {
        "level": "intermediate",
        "tone": "friendly",
        "solution_policy": "hints_first",
    }

    listed = client.get(
        f"/v1/student/courses/{room.course_id}/conversations", headers=student.headers
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["preview"] == COVERED_QUESTION[:120]

    detail = client.get(
        f"/v1/student/courses/{room.course_id}/conversations/{conversation['id']}",
        headers=student.headers,
    ).json()
    assert [m["author"] for m in detail["messages"]] == ["student", "tutor"]
    assert detail["messages"][1]["correction"] is None


def test_citation_becomes_unavailable_after_exclusion(client, teacher, student) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)

    client.post(
        f"/v1/teacher/courses/{room.course_id}/documents/{room.document['id']}/exclude",
        headers=teacher.headers,
    )

    detail = client.get(
        f"/v1/student/courses/{room.course_id}/conversations/{conversation['id']}",
        headers=student.headers,
    ).json()
    citation = detail["messages"][1]["citations"][0]
    assert citation["available"] is False
    assert citation["passage"] is None
    assert citation["document_name"] == "ecuaciones.md"


def test_conversations_are_private_to_their_student(
    client, teacher, student, other_student
) -> None:
    room = classroom(client, teacher, student)
    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    conversation = open_conversation(client, student, room.course_id)
    path = f"/v1/student/courses/{room.course_id}/conversations/{conversation['id']}"

    assert client.get(path, headers=other_student.headers).status_code == 404
    assert (
        client.post(
            f"{path}/messages", headers=other_student.headers, json={"text": "hola"}
        ).status_code
        == 404
    )


def test_prompt_never_contains_identifying_data(client, teacher, student, llm) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)

    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)

    system, messages = llm.chat_calls[0]
    sent = system + "".join(m["content"] for m in messages)
    assert "Lucas" not in sent
    assert str(student.id) not in sent
    assert "@" not in sent
