"""US1–US4 (spec 022) — a repeated mistake is overcome after correct exercises."""

import pytest

from tests.api.helpers import classroom
from tests.api.test_next_steps import steps
from tests.api.test_pedagogy_criteria import set_course
from tests.api.test_progress import graded, progress, topic_of
from tests.api.test_repeated_mistakes import read
from tests.api.test_us6_topics import create_topic


@pytest.fixture
def room(client, teacher, student):
    room = classroom(client, teacher, student)
    topics = [
        create_topic(client, teacher, room.course_id, name).json()
        for name in ("Paréntesis", "Transponer")
    ]
    return room.course_id, topics


def mistakes(db, course_id, student, topic, days=(10, 9, 8), error_type="procedural"):
    return [
        graded(db, course_id, student, d, "incorrect", topic, error_type=error_type)
        for d in days
    ]


def overcome(client, student, course_id: str, submission_id) -> list[dict]:
    return read(client, student, course_id, str(submission_id))["overcome"]


def test_the_third_correct_exercise_overcomes_the_pattern(
    client, db, student, room
) -> None:
    course_id, (parens, _) = room
    mistakes(db, course_id, student, parens)
    correct = [graded(db, course_id, student, d, "correct", parens) for d in (5, 4, 3)]

    assert overcome(client, student, course_id, correct[2]) == [
        {
            "error_type": "procedural",
            "topic_name": "Paréntesis",
            "count": 3,
            "correct": 3,
        }
    ]


def test_it_is_said_only_once(client, db, student, room) -> None:
    course_id, (parens, _) = room
    mistakes(db, course_id, student, parens)
    correct = [
        graded(db, course_id, student, d, "correct", parens) for d in (5, 4, 3, 2)
    ]

    assert overcome(client, student, course_id, correct[1]) == []
    assert overcome(client, student, course_id, correct[3]) == []


def test_another_result_in_the_topic_restarts_the_count(
    client, db, student, room
) -> None:
    course_id, (parens, transpose) = room
    mistakes(db, course_id, student, parens)
    graded(db, course_id, student, 6, "correct", parens)
    graded(db, course_id, student, 5, "partially_correct", parens, "conceptual")
    # Other topics do not count, nor break the run.
    graded(db, course_id, student, 4.5, "incorrect", transpose)
    correct = [graded(db, course_id, student, d, "correct", parens) for d in (4, 3, 2)]

    assert overcome(client, student, course_id, correct[1]) == []
    assert [
        o["error_type"] for o in overcome(client, student, course_id, correct[2])
    ] == ["procedural"]


def test_mistakes_that_never_repeated_are_not_celebrated(
    client, db, student, room
) -> None:
    course_id, (parens, _) = room
    mistakes(db, course_id, student, parens, days=(10, 9))
    correct = [graded(db, course_id, student, d, "correct", parens) for d in (5, 4, 3)]

    assert overcome(client, student, course_id, correct[2]) == []


def test_progress_says_how_far_each_mistake_is(
    client, db, teacher, student, room
) -> None:
    course_id, (parens, _) = room
    mistakes(db, course_id, student, parens)
    for d in (5, 4):
        graded(db, course_id, student, d, "correct", parens)

    error = topic_of(progress(client, student, course_id).json(), "Paréntesis")[
        "top_errors"
    ][0]
    assert error["correct_since"] == 2
    assert error["overcome"] is False

    graded(db, course_id, student, 3, "correct", parens)
    body = progress(client, student, course_id).json()
    error = topic_of(body, "Paréntesis")["top_errors"][0]
    assert error["correct_since"] == 3
    assert error["overcome"] is True
    assert progress(client, teacher, course_id, student).json() == body


def test_next_steps_skip_overcome_patterns(client, db, student, room) -> None:
    course_id, (parens, transpose) = room
    mistakes(db, course_id, student, parens, days=(10, 9, 8, 7))
    mistakes(db, course_id, student, transpose, error_type="conceptual")
    for d in (5, 4, 3):
        graded(db, course_id, student, d, "correct", parens)

    review = [
        s for s in steps(client, student, course_id) if s["kind"] == "review_mistake"
    ]

    assert [(r["error_type"], r["topic_name"]) for r in review] == [
        ("conceptual", "Transponer")
    ]


def test_overcome_after_is_a_course_criterion(
    client, db, teacher, student, room
) -> None:
    course_id, (parens, _) = room
    set_course(
        client,
        teacher,
        course_id,
        repeated_mistakes={"count": 3, "window_days": 30, "overcome_after": 1},
    )
    mistakes(db, course_id, student, parens)
    correct = graded(db, course_id, student, 5, "correct", parens)

    assert len(overcome(client, student, course_id, correct)) == 1


def test_a_course_group_saved_before_keeps_the_default(client, teacher, room) -> None:
    course_id, _ = room
    body = set_course(
        client, teacher, course_id, repeated_mistakes={"count": 2, "window_days": 30}
    )

    assert body["effective"]["repeated_mistakes"] == {
        "count": 2,
        "window_days": 30,
        "overcome_after": 3,
    }


@pytest.mark.parametrize("value", [0, 21])
def test_invalid_overcome_after_is_rejected(client, teacher, room, value) -> None:
    course_id, _ = room
    response = client.put(
        f"/v1/teacher/courses/{course_id}/pedagogy-criteria",
        headers=teacher.headers,
        json={
            "repeated_mistakes": {
                "count": 3,
                "window_days": 30,
                "overcome_after": value,
            }
        },
    )
    assert response.status_code == 422
