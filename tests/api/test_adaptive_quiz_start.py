"""US1–US3 (spec 021) — quizzes start from mastery and favour weak topics."""

import uuid

import pytest

from app.models import QuizQuestion
from tests.api.helpers import classroom
from tests.api.test_pedagogy_criteria import set_course
from tests.api.test_progress import quiz
from tests.api.test_quizzes import quizzes_path, start
from tests.api.test_us6_topics import create_topic

QUIZ = {"length": 5, "streak": 2, "start_level": 2, "adaptive": True}


def questions(db, course_id: str, topic: dict, levels=(1, 1, 2, 2, 3, 3)) -> None:
    """Approved questions in the topic, one per level given; the right option is 0."""
    for n, level in enumerate(levels):
        db.add(
            QuizQuestion(
                course_id=uuid.UUID(course_id),
                topic_id=uuid.UUID(topic["id"]),
                statement=f"{topic['name']} {n}",
                options=["a", "b", "c", "d"],
                correct_option=0,
                explanation="Porque sí.",
                difficulty=level,
                status="approved",
            )
        )
    db.commit()


def started(client, student, course_id: str, topic: dict | None = None) -> dict:
    response = start(client, student, course_id, topic["id"] if topic else None)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def room(client, db, teacher, student):
    room = classroom(client, teacher, student)
    topics = [
        create_topic(client, teacher, room.course_id, name).json()
        for name in ("Paréntesis", "Transponer")
    ]
    return room.course_id, topics


def test_a_mastered_topic_starts_at_the_top_level(client, db, student, room) -> None:
    course_id, (parens, _) = room
    quiz(db, course_id, student, parens, [True, True, True], 1)
    questions(db, course_id, parens)

    body = started(client, student, course_id, parens)

    assert body["level"] == 3
    assert body["current"]["difficulty"] == 3
    assert body["start_basis"] == {
        "reason": "mastery",
        "mastery_level": "mastered",
        "score": 1.0,
    }


def test_a_starting_topic_starts_at_the_bottom_level(client, db, student, room) -> None:
    course_id, (parens, _) = room
    quiz(db, course_id, student, parens, [True, False, False, False, False], 1)
    questions(db, course_id, parens)

    body = started(client, student, course_id, parens)

    assert body["level"] == 1
    assert body["start_basis"]["mastery_level"] == "starting"
    assert body["start_basis"]["score"] == pytest.approx(0.2)


def test_without_a_score_the_quiz_starts_at_the_default(
    client, db, student, room
) -> None:
    course_id, (parens, _) = room
    quiz(db, course_id, student, parens, [True], 1)
    questions(db, course_id, parens)

    body = started(client, student, course_id, parens)

    assert body["level"] == 2
    assert body["start_basis"] == {
        "reason": "no_score",
        "mastery_level": None,
        "score": None,
    }


def test_a_fixed_start_ignores_mastery(client, db, teacher, student, room) -> None:
    course_id, (parens, _) = room
    set_course(client, teacher, course_id, quiz={**QUIZ, "adaptive": False})
    quiz(db, course_id, student, parens, [True, True, True], 1)
    questions(db, course_id, parens)

    body = started(client, student, course_id, parens)

    assert body["level"] == 2
    assert body["start_basis"]["reason"] == "fixed"


def test_a_quiz_on_every_topic_starts_from_the_mean(client, db, student, room) -> None:
    course_id, (parens, solve) = room
    quiz(db, course_id, student, parens, [True, True, True, True, True], 2)
    quiz(db, course_id, student, solve, [True, False, False, False, False], 1)
    questions(db, course_id, parens)

    body = started(client, student, course_id)

    assert body["level"] == 2
    assert body["start_basis"] == {
        "reason": "mastery",
        "mastery_level": "progressing",
        "score": pytest.approx(0.6),
    }


def test_a_quiz_on_every_topic_favours_the_weak_one(client, db, student, room) -> None:
    course_id, (parens, solve) = room
    quiz(db, course_id, student, parens, [True, True, True, True, False], 2)
    quiz(db, course_id, student, solve, [True, True, False, False, False], 1)
    # The strong topic's questions are older: without weighting they would come first.
    questions(db, course_id, parens, levels=(2, 2))
    questions(db, course_id, solve, levels=(2, 2))

    body = started(client, student, course_id)

    assert body["current"]["topic_name"] == "Transponer"


def test_without_adaptive_the_order_is_unchanged(
    client, db, teacher, student, room
) -> None:
    course_id, (parens, solve) = room
    set_course(client, teacher, course_id, quiz={**QUIZ, "adaptive": False})
    quiz(db, course_id, student, parens, [True, True, True, True, False], 2)
    quiz(db, course_id, student, solve, [True, True, False, False, False], 1)
    questions(db, course_id, parens, levels=(2, 2))
    questions(db, course_id, solve, levels=(2, 2))

    body = started(client, student, course_id)

    assert body["current"]["topic_name"] == "Paréntesis"


def test_a_course_sets_the_length_and_the_streak(
    client, db, teacher, student, room
) -> None:
    course_id, (parens, _) = room
    set_course(
        client,
        teacher,
        course_id,
        quiz={"length": 3, "streak": 1, "start_level": 1, "adaptive": False},
    )
    questions(db, course_id, parens)

    body = started(client, student, course_id, parens)
    assert body["question_count"] == 3
    assert body["level"] == 1

    response = client.post(
        f"{quizzes_path(course_id)}/{body['id']}/answers",
        headers=student.headers,
        json={"question_id": body["current"]["id"], "choice": 0},
    )

    assert response.status_code == 200, response.text
    assert response.json()["quiz"]["level"] == 2
    assert response.json()["difficulty_change"]["reason"] == "correct_streak"


@pytest.mark.parametrize(
    "change",
    [{"length": 0}, {"length": 31}, {"streak": 0}, {"streak": 11}, {"start_level": 4}],
)
def test_invalid_quiz_criteria_are_rejected(client, teacher, room, change) -> None:
    course_id, _ = room
    response = client.put(
        f"/v1/teacher/courses/{course_id}/pedagogy-criteria",
        headers=teacher.headers,
        json={"quiz": {**QUIZ, **change}},
    )
    assert response.status_code == 422


def test_the_start_basis_is_kept_with_the_quiz(client, db, student, room) -> None:
    course_id, (parens, _) = room
    quiz(db, course_id, student, parens, [True, True, True], 1)
    questions(db, course_id, parens)
    body = started(client, student, course_id, parens)
    # More activity later does not change why this quiz started where it did.
    quiz(db, course_id, student, parens, [False] * 10, 0)

    response = client.get(
        f"{quizzes_path(course_id)}/{body['id']}", headers=student.headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["start_basis"]["mastery_level"] == "mastered"
