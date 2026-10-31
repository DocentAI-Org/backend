"""US3–US4 (spec 008) — students take each phase once; the teacher reads the results."""

import pytest

from tests.api.helpers import classroom, give_consent
from tests.api.test_course_test_setup import add_question, base, set_phase
from tests.api.test_us6_topics import create_topic


def student_base(course_id: str) -> str:
    return f"/v1/student/courses/{course_id}/test"


def submit(client, user, course_id: str, phase: str, answers: list[dict]):
    return client.post(
        f"{student_base(course_id)}/{phase}",
        headers=user.headers,
        json={"answers": answers},
    )


@pytest.fixture
def ready(client, teacher, student):
    """Two questions in "Paréntesis" and one in "Despejar"; the pre-test is open."""
    room = classroom(client, teacher, student)
    parens = create_topic(client, teacher, room.course_id, "Paréntesis").json()
    solve = create_topic(client, teacher, room.course_id, "Despejar").json()
    questions = [
        add_question(client, teacher, room.course_id, parens["id"]).json(),
        add_question(
            client,
            teacher,
            room.course_id,
            parens["id"],
            statement="Otra",
            correct_option=1,
        ).json(),
        add_question(
            client,
            teacher,
            room.course_id,
            solve["id"],
            statement="3x = 12",
            correct_option=2,
        ).json(),
    ]
    assert set_phase(client, teacher, room.course_id, "pre", "open").status_code == 200
    return room, questions


def answers(questions: list[dict], right: list[bool]) -> list[dict]:
    return [
        {
            "question_id": q["id"],
            "choice": q["correct_option"] if ok else (q["correct_option"] + 1) % 4,
        }
        for q, ok in zip(questions, right, strict=True)
    ]


def test_the_student_sees_each_phase_and_takes_the_open_one(
    client, student, ready
) -> None:
    room, questions = ready

    phases = client.get(student_base(room.course_id), headers=student.headers)
    test = client.get(f"{student_base(room.course_id)}/pre", headers=student.headers)

    assert phases.status_code == 200, phases.text
    assert phases.json() == [
        {"phase": "pre", "status": "open", "done": False, "question_count": 3},
        {"phase": "post", "status": "not_open", "done": False, "question_count": 3},
    ]
    body = test.json()
    assert body["done"] is False
    assert [q["id"] for q in body["questions"]] == [q["id"] for q in questions]
    assert "correct_option" not in body["questions"][0]
    assert body["questions"][0]["topic_name"] == "Paréntesis"


def test_a_submission_says_nothing_about_right_or_wrong(client, student, ready) -> None:
    room, questions = ready

    response = submit(
        client, student, room.course_id, "pre", answers(questions, [True] * 3)
    )

    assert response.status_code == 201, response.text
    assert set(response.json()) == {"phase", "submitted_at"}
    again = client.get(f"{student_base(room.course_id)}/pre", headers=student.headers)
    assert again.json()["done"] is True
    assert again.json()["questions"] == []


def test_every_question_must_be_answered_once(client, student, ready) -> None:
    room, questions = ready
    full = answers(questions, [True] * 3)

    for bad in (
        full[:2],
        [*full[:2], {"question_id": full[0]["question_id"], "choice": 1}],
        [
            *full[:2],
            {"question_id": "00000000-0000-0000-0000-000000000000", "choice": 0},
        ],
        [*full[:2], {"question_id": full[2]["question_id"], "choice": 4}],
    ):
        assert submit(client, student, room.course_id, "pre", bad).status_code == 422


def test_each_phase_is_taken_once_and_only_while_open(
    client, teacher, student, ready
) -> None:
    room, questions = ready
    submit(client, student, room.course_id, "pre", answers(questions, [True] * 3))

    twice = submit(
        client, student, room.course_id, "pre", answers(questions, [True] * 3)
    )
    closed = submit(
        client, student, room.course_id, "post", answers(questions, [True] * 3)
    )
    reading = client.get(
        f"{student_base(room.course_id)}/post", headers=student.headers
    )

    assert twice.status_code == closed.status_code == reading.status_code == 409
    assert twice.json()["error"]["code"] == "test_already_done"
    assert closed.json()["error"]["code"] == "test_not_open"


def test_taking_the_test_needs_consent(client, teacher, student, ready) -> None:
    room, questions = ready
    client.delete("/v1/student/consent", headers=student.headers)

    blocked = submit(
        client, student, room.course_id, "pre", answers(questions, [True] * 3)
    )

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "consent_required"
    give_consent(client, student)
    assert (
        submit(
            client, student, room.course_id, "pre", answers(questions, [True] * 3)
        ).status_code
        == 201
    )


def test_results_by_student_phase_and_topic(
    client, teacher, student, other_student, ready
) -> None:
    room, questions = ready
    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    submit(
        client, student, room.course_id, "pre", answers(questions, [True, False, False])
    )
    set_phase(client, teacher, room.course_id, "pre", "closed")
    set_phase(client, teacher, room.course_id, "post", "open")
    submit(
        client, student, room.course_id, "post", answers(questions, [True, True, True])
    )

    response = client.get(f"{base(room.course_id)}/results", headers=teacher.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question_count"] == 3
    rows = {s["display_name"]: s for s in body["students"]}
    mine = rows[student.display_name]
    assert (mine["pre"]["right"], mine["pre"]["total"]) == (1, 3)
    assert [
        (t["topic_name"], t["right"], t["total"]) for t in mine["pre"]["by_topic"]
    ] == [
        ("Paréntesis", 1, 2),
        ("Despejar", 0, 1),
    ]
    assert (mine["post"]["right"], mine["post"]["total"]) == (3, 3)
    assert rows[other_student.display_name]["pre"] is None
    pre = next(a for a in body["averages"] if a["phase"] == "pre")
    assert pre["submitted"] == 1
    assert pre["score"] == pytest.approx(1 / 3)
    assert [(t["topic_name"], t["score"]) for t in pre["by_topic"]] == [
        ("Paréntesis", 0.5),
        ("Despejar", 0.0),
    ]
    phases = {p["phase"]: p for p in body["phases"]}
    assert (phases["pre"]["submitted_count"], phases["post"]["submitted_count"]) == (
        1,
        1,
    )


def test_students_of_other_courses_get_404(client, other_student, ready) -> None:
    room, _ = ready

    response = client.get(student_base(room.course_id), headers=other_student.headers)

    assert response.status_code == 404
