"""002 US1 — students give, review and revoke study consent."""

from app.core.config import get_settings
from tests.api.helpers import (
    COVERED_QUESTION,
    ask,
    classroom,
    give_consent,
    open_conversation,
)
from tests.api.test_us7_exercises import EXERCISE


def test_consent_starts_not_given(client, student) -> None:
    body = client.get("/v1/student/consent", headers=student.headers).json()

    assert body == {
        "given": False,
        "version": None,
        "given_at": None,
        "current_version": "2026-10",
    }


def test_give_and_revoke_are_recorded_in_the_history(client, student) -> None:
    given = client.post("/v1/student/consent", headers=student.headers)
    assert given.status_code == 200
    assert given.json()["given"] is True
    assert given.json()["version"] == "2026-10"
    assert given.json()["given_at"]

    again = client.post("/v1/student/consent", headers=student.headers)
    assert again.json()["given_at"] == given.json()["given_at"]

    revoked = client.delete("/v1/student/consent", headers=student.headers).json()
    assert revoked["given"] is False
    client.delete("/v1/student/consent", headers=student.headers)

    history = client.get("/v1/student/consent/history", headers=student.headers).json()
    assert [e["action"] for e in history] == ["given", "revoked"]
    assert all(e["version"] == "2026-10" for e in history)


def test_tutor_and_exercises_require_consent(client, db, teacher, student, llm) -> None:
    room = classroom(client, teacher, student, consent=False)
    conversation = open_conversation(client, student, room.course_id)

    blocked = ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    exercise = client.post(
        f"/v1/student/courses/{room.course_id}/submissions",
        headers=student.headers,
        json=EXERCISE,
    )

    for response in (blocked, exercise):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "consent_required"
    assert llm.chat_calls == []
    allowance = client.get("/v1/student/allowance", headers=student.headers).json()
    assert allowance["used"] == 0

    give_consent(client, student)
    accepted = ask(
        client, student, room.course_id, conversation["id"], COVERED_QUESTION
    )
    assert accepted.status_code == 201

    client.delete("/v1/student/consent", headers=student.headers)
    again = ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    assert again.json()["error"]["code"] == "consent_required"

    # Revoking keeps read access to the student's own data.
    detail = client.get(
        f"/v1/student/courses/{room.course_id}/conversations/{conversation['id']}",
        headers=student.headers,
    )
    assert detail.status_code == 200


def test_new_consent_version_requires_consenting_again(
    client, student, monkeypatch
) -> None:
    give_consent(client, student)
    monkeypatch.setattr(get_settings(), "consent_version", "2027-01")

    body = client.get("/v1/student/consent", headers=student.headers).json()

    assert body["given"] is False
    assert body["version"] == "2026-10"
    assert body["current_version"] == "2027-01"


def test_history_is_private_and_consent_is_for_students(
    client, student, other_student, teacher
) -> None:
    give_consent(client, other_student)

    history = client.get("/v1/student/consent/history", headers=student.headers).json()
    assert history == []
    assert (
        client.post("/v1/student/consent", headers=teacher.headers).status_code == 403
    )
