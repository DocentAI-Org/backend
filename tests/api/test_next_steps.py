"""US1–US2 (spec 020) — recommended next steps, the same for both roles."""

import uuid

import pytest

from app.models import MistakeReview, QuizQuestion
from tests.api.helpers import classroom
from tests.api.test_course_test_setup import add_question, set_phase
from tests.api.test_progress import graded, quiz
from tests.api.test_quizzes import start
from tests.api.test_us6_topics import create_topic


def steps(client, user, course_id: str, student=None) -> list[dict]:
    path = (
        f"/v1/teacher/courses/{course_id}/students/{student.id}/next-steps"
        if student
        else f"/v1/student/courses/{course_id}/next-steps"
    )
    response = client.get(path, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()["steps"]


def kinds(found: list[dict]) -> list[str]:
    return [step["kind"] for step in found]


def of_kind(found: list[dict], kind: str) -> dict:
    return next(step for step in found if step["kind"] == kind)


def approved(db, course_id: str, topic: dict, count: int = 2) -> None:
    for n in range(count):
        db.add(
            QuizQuestion(
                course_id=uuid.UUID(course_id),
                topic_id=uuid.UUID(topic["id"]),
                statement=f"Pregunta {n}",
                options=["a", "b", "c", "d"],
                correct_option=0,
                explanation="Porque sí.",
                difficulty=2,
                status="approved",
            )
        )
    db.commit()


@pytest.fixture
def room(client, teacher, student):
    room = classroom(client, teacher, student)
    topics = [
        create_topic(client, teacher, room.course_id, name).json()
        for name in ("Paréntesis", "Transponer", "Despejar")
    ]
    return room.course_id, topics


def test_with_no_activity_the_first_topic_comes_first(
    client, db, student, room
) -> None:
    course_id, topics = room
    approved(db, course_id, topics[0])

    found = steps(client, student, course_id)

    assert found == [
        {
            "kind": "start_topic",
            "topic_id": topics[0]["id"],
            "topic_name": "Paréntesis",
            "level": "not_started",
            "items": 0,
            "min_items": 3,
            "has_questions": True,
        }
    ]


def test_a_topic_with_too_few_items_is_still_to_start(
    client, db, student, room
) -> None:
    course_id, topics = room
    graded(db, course_id, student, 1, "correct", topics[0])

    (step,) = steps(client, student, course_id)

    assert step["topic_name"] == "Paréntesis"
    assert step["level"] == "insufficient"
    assert step["items"] == 1
    assert step["has_questions"] is False


def test_the_weakest_topic_is_practised(client, db, student, room) -> None:
    course_id, topics = room
    quiz(db, course_id, student, topics[0], [True, True, False, False], 3)
    quiz(db, course_id, student, topics[1], [True, False, False, False, False], 2)
    for topic in topics:
        approved(db, course_id, topic)

    found = steps(client, student, course_id)

    assert kinds(found) == ["practice_topic", "start_topic"]
    practice = found[0]
    assert practice["topic_name"] == "Transponer"
    assert practice["level"] == "starting"
    assert practice["score"] == pytest.approx(0.2)
    assert practice["items"] == 5
    assert practice["has_questions"] is True
    assert found[1]["topic_name"] == "Despejar"


def test_everything_mastered_leaves_nothing(client, db, student, room) -> None:
    course_id, topics = room
    for topic in topics:
        quiz(db, course_id, student, topic, [True, True, True], 1)

    assert steps(client, student, course_id) == []


def test_a_repeated_mistake_is_reviewed(client, db, student, room) -> None:
    course_id, topics = room
    made = [
        graded(db, course_id, student, days, "incorrect", topics[0])
        for days in (5, 3, 1)
    ]
    graded(db, course_id, student, 2, "incorrect", topics[1], error_type="conceptual")

    review = of_kind(steps(client, student, course_id), "review_mistake")

    assert review == {
        "kind": "review_mistake",
        "error_type": "procedural",
        "topic_id": topics[0]["id"],
        "topic_name": "Paréntesis",
        "count": 3,
        "window_days": 30,
        "submission_id": str(made[-1]),
        "reviewed": False,
    }

    db.add(
        MistakeReview(
            submission_id=made[-1],
            course_id=uuid.UUID(course_id),
            student_id=student.id,
            error_type="procedural",
            topic_name="Paréntesis",
            kind="answer",
            explanation="El 2 multiplica a cada término.",
        )
    )
    db.commit()
    review = of_kind(steps(client, student, course_id), "review_mistake")
    assert review["reviewed"] is True


def test_old_or_few_mistakes_are_not_a_step(client, db, student, room) -> None:
    course_id, topics = room
    for days in (60, 50, 1):
        graded(db, course_id, student, days, "incorrect", topics[0])

    assert "review_mistake" not in kinds(steps(client, student, course_id))


def test_an_unfinished_quiz_is_resumed(client, db, student, room) -> None:
    course_id, topics = room
    approved(db, course_id, topics[1], count=3)
    started = start(client, student, course_id, topics[1]["id"]).json()

    found = steps(client, student, course_id)

    assert found[0] == {
        "kind": "resume_quiz",
        "quiz_id": started["id"],
        "topic_name": "Transponer",
        "answered": 0,
        "total": 3,
    }


def test_an_open_test_comes_first_until_taken(
    client, teacher, db, student, room
) -> None:
    course_id, topics = room
    question = add_question(client, teacher, course_id, topics[0]["id"]).json()
    set_phase(client, teacher, course_id, "pre", "open")

    assert steps(client, student, course_id)[0] == {"kind": "test", "phase": "pre"}

    response = client.post(
        f"/v1/student/courses/{course_id}/test/pre",
        headers=student.headers,
        json={"answers": [{"question_id": question["id"], "choice": 0}]},
    )
    assert response.status_code in (200, 201), response.text
    assert "test" not in kinds(steps(client, student, course_id))


def test_at_most_three_steps_by_rank(client, teacher, db, student, room) -> None:
    course_id, topics = room
    question = add_question(client, teacher, course_id, topics[0]["id"])
    assert question.status_code == 201, question.text
    set_phase(client, teacher, course_id, "pre", "open")
    approved(db, course_id, topics[2])
    start(client, student, course_id, topics[2]["id"])
    for days in (3, 2, 1):
        graded(db, course_id, student, days, "incorrect", topics[0])

    assert kinds(steps(client, student, course_id)) == [
        "test",
        "resume_quiz",
        "review_mistake",
    ]


def test_the_teacher_sees_the_same_steps(
    client, db, teacher, other_teacher, student, room
) -> None:
    course_id, topics = room
    quiz(db, course_id, student, topics[0], [True, False, False], 1)

    assert steps(client, teacher, course_id, student) == steps(
        client, student, course_id
    )
    response = client.get(
        f"/v1/teacher/courses/{course_id}/students/{student.id}/next-steps",
        headers=other_teacher.headers,
    )
    assert response.status_code == 404
