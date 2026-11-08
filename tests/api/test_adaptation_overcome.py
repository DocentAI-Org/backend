"""US1 (spec 023) — the tutor's adaptation leaves out the patterns already overcome."""

import pytest

from tests.api.helpers import classroom
from tests.api.test_adaptation import chat
from tests.api.test_progress import graded
from tests.api.test_us6_topics import create_topic
from tests.api.test_us7_exercises import submit


@pytest.fixture
def room(client, teacher, student):
    room = classroom(client, teacher, student)
    topics = [
        create_topic(client, teacher, room.course_id, name).json()
        for name in ("Paréntesis", "Transponer")
    ]
    return room.course_id, topics


def mistakes(db, course_id, student, topic, days, error_type="procedural"):
    for d in days:
        graded(db, course_id, student, d, "incorrect", topic, error_type=error_type)


def corrects(db, course_id, student, topic, days):
    for d in days:
        graded(db, course_id, student, d, "correct", topic)
    db.commit()


def test_an_overcome_pattern_is_not_minded(client, db, llm, student, room) -> None:
    course_id, (parens, _) = room
    mistakes(db, course_id, student, parens, (10, 9, 8))
    corrects(db, course_id, student, parens, (5, 4, 3))

    assert chat(client, student, course_id)["tutor_message"]["adaptation"] is None
    system, _ = llm.chat_calls[-1]
    assert "procedimiento" not in system.lower()
    assert submit(client, student, course_id).json()["adaptation"] is None


def test_another_repeated_type_is_minded_instead(
    client, db, llm, student, room
) -> None:
    course_id, (parens, transpose) = room
    mistakes(db, course_id, student, parens, (10, 9, 8, 7))
    mistakes(db, course_id, student, transpose, (9.5, 8.5, 7.5), "conceptual")
    corrects(db, course_id, student, parens, (5, 4, 3))

    assert chat(client, student, course_id)["tutor_message"]["adaptation"] == {
        "error_type": "conceptual",
        "count": 3,
        "window_days": 30,
    }


def test_mistakes_in_other_topics_still_count(client, db, llm, student, room) -> None:
    course_id, (parens, transpose) = room
    mistakes(db, course_id, student, parens, (10, 9, 8))
    mistakes(db, course_id, student, transpose, (7, 6, 5.5))
    corrects(db, course_id, student, parens, (5, 4, 3))

    adaptation = chat(client, student, course_id)["tutor_message"]["adaptation"]
    assert adaptation["error_type"] == "procedural"
    assert adaptation["count"] == 3


def test_a_new_mistake_brings_the_pattern_back(client, db, llm, student, room) -> None:
    course_id, (parens, _) = room
    mistakes(db, course_id, student, parens, (10, 9, 8))
    corrects(db, course_id, student, parens, (5, 4, 3))
    mistakes(db, course_id, student, parens, (2,))
    db.commit()

    adaptation = chat(client, student, course_id)["tutor_message"]["adaptation"]
    assert adaptation["error_type"] == "procedural"
    assert adaptation["count"] == 4
