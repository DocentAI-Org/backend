"""US1–US2 (spec 008) — the teacher prepares the test and opens each phase."""

from tests.api.test_quiz_questions import approved_questions
from tests.api.test_us2_courses import create_course
from tests.api.test_us6_topics import create_topic

OPTIONS = ["2x - 6", "2x - 3", "2x + 6", "x - 6"]


def base(course_id: str) -> str:
    return f"/v1/teacher/courses/{course_id}/test"


def add_question(client, teacher, course_id: str, topic_id: str, **changes):
    body = {
        "topic_id": topic_id,
        "statement": "¿Qué queda al quitar el paréntesis en 2(x - 3)?",
        "options": OPTIONS,
        "correct_option": 0,
    } | changes
    return client.post(
        f"{base(course_id)}/questions", headers=teacher.headers, json=body
    )


def set_phase(client, teacher, course_id: str, phase: str, status: str):
    return client.put(
        f"{base(course_id)}/phases/{phase}",
        headers=teacher.headers,
        json={"status": status},
    )


def course_with_topics(client, teacher):
    course = create_course(client, teacher)
    topics = [
        create_topic(client, teacher, course["id"], name).json()
        for name in ("Paréntesis", "Despejar")
    ]
    return course, topics


def test_questions_are_added_listed_edited_and_deleted(client, teacher) -> None:
    course, (parens, solve) = course_with_topics(client, teacher)

    first = add_question(client, teacher, course["id"], parens["id"])
    second = add_question(
        client, teacher, course["id"], solve["id"], statement="Despeja x en 3x = 12"
    )
    assert first.status_code == second.status_code == 201, first.text
    assert first.json()["topic_name"] == "Paréntesis"
    assert (first.json()["position"], second.json()["position"]) == (1, 2)

    edited = client.patch(
        f"{base(course['id'])}/questions/{second.json()['id']}",
        headers=teacher.headers,
        json={"statement": "Despeja x en 4x = 20", "correct_option": 2},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["correct_option"] == 2

    deleted = client.delete(
        f"{base(course['id'])}/questions/{first.json()['id']}", headers=teacher.headers
    )
    assert deleted.status_code == 204

    test = client.get(base(course["id"]), headers=teacher.headers).json()
    assert [q["statement"] for q in test["questions"]] == ["Despeja x en 4x = 20"]
    assert test["locked"] is False
    assert [(p["phase"], p["status"]) for p in test["phases"]] == [
        ("pre", "not_open"),
        ("post", "not_open"),
    ]


def test_an_approved_quiz_question_can_be_copied(client, llm, teacher, student) -> None:
    room, topic, made = approved_questions(client, llm, teacher, student)

    response = client.post(
        f"{base(room.course_id)}/questions/from-quiz",
        headers=teacher.headers,
        json={"question_id": made[0]["id"]},
    )

    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["statement"] == made[0]["statement"]
    assert copy["options"] == made[0]["options"]
    assert copy["correct_option"] == made[0]["correct_option"]
    assert copy["topic_id"] == topic["id"]
    assert copy["id"] != made[0]["id"]


def test_invalid_questions_are_rejected(client, teacher, other_teacher) -> None:
    course, (parens, _) = course_with_topics(client, teacher)
    foreign, (foreign_topic, _) = course_with_topics(client, other_teacher)

    for changes in (
        {"options": ["a", "b", "c"]},
        {"options": ["a", "a", "b", "c"]},
        {"correct_option": 4},
        {"statement": ""},
    ):
        response = add_question(client, teacher, course["id"], parens["id"], **changes)
        assert response.status_code == 422, changes
    unknown_topic = add_question(client, teacher, course["id"], foreign_topic["id"])
    assert unknown_topic.status_code == 422


def test_opening_needs_questions_and_freezes_them(client, teacher) -> None:
    course, (parens, _) = course_with_topics(client, teacher)

    empty = set_phase(client, teacher, course["id"], "pre", "open")
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "test_empty"

    question = add_question(client, teacher, course["id"], parens["id"]).json()
    opened = set_phase(client, teacher, course["id"], "pre", "open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["status"] == "open"
    assert opened.json()["opened_at"] is not None

    for response in (
        add_question(client, teacher, course["id"], parens["id"]),
        client.patch(
            f"{base(course['id'])}/questions/{question['id']}",
            headers=teacher.headers,
            json={"statement": "Otra"},
        ),
        client.delete(
            f"{base(course['id'])}/questions/{question['id']}", headers=teacher.headers
        ),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "test_locked"
    assert client.get(base(course["id"]), headers=teacher.headers).json()["locked"]


def test_phases_close_and_reopen(client, teacher) -> None:
    course, (parens, _) = course_with_topics(client, teacher)
    add_question(client, teacher, course["id"], parens["id"])
    set_phase(client, teacher, course["id"], "pre", "open")

    closed = set_phase(client, teacher, course["id"], "pre", "closed").json()
    post = set_phase(client, teacher, course["id"], "post", "open").json()
    reopened = set_phase(client, teacher, course["id"], "pre", "open").json()

    assert closed["status"] == "closed" and closed["closed_at"] is not None
    assert post["status"] == "open"
    assert reopened["status"] == "open"


def test_other_teachers_and_students_are_kept_out(
    client, teacher, other_teacher, student
) -> None:
    course, (parens, _) = course_with_topics(client, teacher)

    assert (
        client.get(base(course["id"]), headers=other_teacher.headers).status_code == 404
    )
    assert (
        add_question(client, other_teacher, course["id"], parens["id"]).status_code
        == 404
    )
    assert client.get(base(course["id"]), headers=student.headers).status_code == 403
