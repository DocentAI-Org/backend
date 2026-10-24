"""US5 — teacher configures the tutor (T3)."""

from tests.api.helpers import COVERED_QUESTION, ask, classroom, open_conversation
from tests.api.test_us2_courses import create_course


def test_new_course_has_default_settings(client, teacher) -> None:
    course = create_course(client, teacher)

    settings = client.get(
        f"/v1/teacher/courses/{course['id']}/tutor-settings", headers=teacher.headers
    ).json()

    assert settings["level"] == "intermediate"
    assert settings["tone"] == "friendly"
    assert settings["solution_policy"] == "hints_first"
    assert settings["updated_at"]


def test_teacher_updates_settings_and_invalid_values_are_rejected(
    client, teacher
) -> None:
    course = create_course(client, teacher)
    path = f"/v1/teacher/courses/{course['id']}/tutor-settings"

    updated = client.put(
        path,
        headers=teacher.headers,
        json={"level": "advanced", "tone": "formal", "solution_policy": "direct"},
    )
    assert updated.status_code == 200
    assert updated.json()["solution_policy"] == "direct"

    invalid = client.put(
        path,
        headers=teacher.headers,
        json={"level": "expert", "tone": "formal", "solution_policy": "direct"},
    )
    assert invalid.status_code == 422
    fields = invalid.json()["error"]["details"]["fields"]
    assert fields[0]["loc"] == ["body", "level"]


def test_new_settings_apply_to_the_next_reply(client, teacher, student, llm) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    client.put(
        f"/v1/teacher/courses/{room.course_id}/tutor-settings",
        headers=teacher.headers,
        json={"level": "basic", "tone": "formal", "solution_policy": "hints_only"},
    )

    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)

    system_prompt = llm.chat_calls[-1][0]
    assert "Nivel del curso: básico" in system_prompt
    assert "Tono: formal" in system_prompt
    assert "nunca des la solución completa" in system_prompt


def test_other_teacher_and_students_cannot_change_settings(
    client, teacher, other_teacher, student
) -> None:
    course = create_course(client, teacher)
    path = f"/v1/teacher/courses/{course['id']}/tutor-settings"
    body = {"level": "basic", "tone": "neutral", "solution_policy": "direct"}

    assert client.put(path, headers=other_teacher.headers, json=body).status_code == 404
    assert client.put(path, headers=student.headers, json=body).status_code == 403
