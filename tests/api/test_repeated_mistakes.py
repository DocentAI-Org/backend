"""US1 (spec 005) — the feedback names a repeated mistake pattern."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models import LearningRecordEntry
from tests.api.helpers import classroom
from tests.api.test_us6_topics import create_topic
from tests.api.test_us7_exercises import MISTAKE, submit


def mistakes(
    client, llm, student, course_id: str, count: int, reply=None
) -> list[dict]:
    llm.reply = reply or MISTAKE
    made = []
    for _ in range(count):
        response = submit(client, student, course_id)
        assert response.status_code == 201, response.text
        made.append(response.json())
    return made


def repeated_room(client, llm, teacher, student, count: int = 3):
    room = classroom(client, teacher, student)
    create_topic(client, teacher, room.course_id, "Paréntesis")
    return room, mistakes(client, llm, student, room.course_id, count)


def read(client, student, course_id: str, submission_id: str) -> dict:
    return client.get(
        f"/v1/student/courses/{course_id}/submissions/{submission_id}",
        headers=student.headers,
    ).json()


def test_the_third_mistake_of_a_type_and_topic_is_a_pattern(
    client, llm, teacher, student
) -> None:
    _, made = repeated_room(client, llm, teacher, student)

    assert made[0]["repeated_mistake"] is None
    assert made[1]["repeated_mistake"] is None
    assert made[2]["repeated_mistake"] == {
        "count": 3,
        "window_days": 30,
        "error_type": "procedural",
        "topic_name": "Paréntesis",
    }


def test_older_reads_keep_their_count(client, llm, teacher, student) -> None:
    room, made = repeated_room(client, llm, teacher, student, count=4)

    assert (
        read(client, student, room.course_id, made[0]["id"])["repeated_mistake"] is None
    )
    assert (
        read(client, student, room.course_id, made[2]["id"])["repeated_mistake"][
            "count"
        ]
        == 3
    )
    assert (
        read(client, student, room.course_id, made[3]["id"])["repeated_mistake"][
            "count"
        ]
        == 4
    )


def test_other_topics_and_old_mistakes_do_not_count(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    create_topic(client, teacher, room.course_id, "Paréntesis")
    create_topic(client, teacher, room.course_id, "Despejar la incógnita")
    mistakes(client, llm, student, room.course_id, 2, MISTAKE | {"topic": "T2"})
    [old] = mistakes(client, llm, student, room.course_id, 1)
    db.execute(
        update(LearningRecordEntry)
        .where(LearningRecordEntry.submission_id == old["id"])
        .values(created_at=datetime.now(UTC) - timedelta(days=31))
    )
    db.commit()

    [latest] = mistakes(client, llm, student, room.course_id, 1)
    assert latest["repeated_mistake"] is None

    [third] = mistakes(
        client, llm, student, room.course_id, 1, MISTAKE | {"topic": "T2"}
    )
    assert third["repeated_mistake"]["topic_name"] == "Despejar la incógnita"


def test_mistakes_without_topic_form_their_own_pattern(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)

    made = mistakes(client, llm, student, room.course_id, 3, MISTAKE | {"topic": None})

    assert made[2]["repeated_mistake"]["topic_name"] is None
    assert made[2]["repeated_mistake"]["count"] == 3


def test_correct_answers_have_no_pattern(client, llm, teacher, student) -> None:
    room, _ = repeated_room(client, llm, teacher, student)

    [correct] = mistakes(
        client,
        llm,
        student,
        room.course_id,
        1,
        {"verdict": "correct", "explanation": "Bien.", "cited": ["F1"]},
    )

    assert correct["repeated_mistake"] is None


def test_unclassified_mistakes_have_no_pattern(client, llm, teacher, student) -> None:
    room, _ = repeated_room(client, llm, teacher, student)

    [odd] = mistakes(
        client, llm, student, room.course_id, 1, MISTAKE | {"error_type": "invented"}
    )

    assert odd["repeated_mistake"] is None


def test_the_teacher_sees_the_same_pattern(client, llm, teacher, student) -> None:
    room, made = repeated_room(client, llm, teacher, student)

    seen = client.get(
        f"/v1/teacher/courses/{room.course_id}/submissions/{made[2]['id']}",
        headers=teacher.headers,
    ).json()

    assert seen["repeated_mistake"] == made[2]["repeated_mistake"]
