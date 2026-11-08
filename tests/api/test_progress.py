"""US1–US2 (spec 007) — progress and mastery by topic, the same for both roles."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import ExerciseSubmission, LearningRecordEntry, Quiz, QuizItem
from tests.api.activity import ago, course_with, risk_of
from tests.api.test_us6_topics import create_topic

MISTAKES = {"incorrect", "partially_correct"}


def graded(
    db,
    course_id: str,
    student,
    days_ago: float,
    verdict: str,
    topic: dict | None = None,
    error_type: str = "procedural",
) -> uuid.UUID:
    """One graded exercise in a topic; mistakes also go to the learning record."""
    is_mistake = verdict in MISTAKES
    submission = ExerciseSubmission(
        course_id=uuid.UUID(course_id),
        student_id=student.id,
        problem_statement="2(x - 3) = 4x + 2",
        worked_answer="2x - 6 = 4x + 2",
        verdict=verdict,
        error_type=error_type if is_mistake else None,
        topic_id=uuid.UUID(topic["id"]) if topic else None,
        topic_name=topic["name"] if topic else None,
        explanation="El 2 multiplica a cada término.",
        explanation_kind="answer" if verdict != "not_assessed" else "no_source",
        saved_to_record=is_mistake,
        created_at=ago(days_ago),
    )
    db.add(submission)
    db.flush()
    if is_mistake:
        db.add(
            LearningRecordEntry(
                course_id=submission.course_id,
                student_id=student.id,
                submission_id=submission.id,
                error_type=error_type,
                topic_id=submission.topic_id,
                topic_name=submission.topic_name,
                created_at=ago(days_ago),
            )
        )
    db.commit()
    return submission.id


def quiz(
    db, course_id: str, student, topic: dict, results: list[bool], days_ago: float
):
    """A completed quiz on the topic with these answers, right or wrong."""
    when = ago(days_ago)
    row = Quiz(
        course_id=uuid.UUID(course_id),
        student_id=student.id,
        topic_id=uuid.UUID(topic["id"]),
        topic_name=topic["name"],
        status="completed",
        question_count=len(results),
        level=2,
        streak=0,
        started_at=when,
        completed_at=when,
    )
    db.add(row)
    db.flush()
    for position, right in enumerate(results, start=1):
        db.add(
            QuizItem(
                quiz_id=row.id,
                position=position,
                topic_id=row.topic_id,
                topic_name=topic["name"],
                statement=f"Pregunta {position}",
                options=["a", "b", "c", "d"],
                correct_option=0,
                explanation="Porque sí.",
                difficulty=2,
                choice=0 if right else 1,
                correct=right,
                answered_at=when + timedelta(seconds=position),
            )
        )
    db.commit()


def progress(client, user, course_id: str, student=None):
    path = (
        f"/v1/teacher/courses/{course_id}/students/{student.id}/progress"
        if student
        else f"/v1/student/courses/{course_id}/progress"
    )
    return client.get(path, headers=user.headers)


@pytest.fixture
def room(client, db, teacher, student):
    course = course_with(client, db, teacher, student, joined_days_ago=60)
    topics = [
        create_topic(client, teacher, course["id"], name).json()
        for name in ("Paréntesis", "Transponer", "Despejar")
    ]
    return course, topics


def topic_of(body: dict, name: str) -> dict:
    return next(t for t in body["topics"] if t["topic_name"] == name)


def test_a_topic_has_level_score_basis_and_criteria(client, db, student, room) -> None:
    course, (parens, *_) = room
    for days, verdict in ((5, "correct"), (4, "partially_correct"), (3, "incorrect")):
        graded(db, course["id"], student, days, verdict, parens)
    quiz(db, course["id"], student, parens, [True, False, True], days_ago=1)

    response = progress(client, student, course["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provisional"] is True
    assert body["criteria"] == {
        "window": 10,
        "min_items": 3,
        "progressing": 0.5,
        "mastered": 0.8,
    }
    assert body["quizzes_completed"] == 1
    topic = topic_of(body, "Paréntesis")
    assert topic["topic_id"] == parens["id"]
    assert topic["level"] == "progressing"
    assert topic["score"] == pytest.approx(3.5 / 6)
    assert topic["basis"] == {
        "exercises_correct": 1,
        "exercises_partial": 1,
        "exercises_total": 3,
        "quiz_right": 2,
        "quiz_total": 3,
    }
    last = datetime.fromisoformat(topic["last_activity_at"])
    assert abs((last - ago(1)).total_seconds()) < 60
    assert body["updated_at"] == topic["last_activity_at"]


def test_only_the_latest_items_count(client, db, student, room) -> None:
    course, (parens, *_) = room
    graded(db, course["id"], student, 20, "incorrect", parens)
    graded(db, course["id"], student, 19, "incorrect", parens)
    quiz(db, course["id"], student, parens, [True] * 10, days_ago=1)

    topic = topic_of(progress(client, student, course["id"]).json(), "Paréntesis")

    assert (topic["level"], topic["score"]) == ("mastered", 1.0)
    assert topic["basis"]["exercises_total"] == 0
    assert topic["basis"]["quiz_total"] == 10


def test_few_or_no_items_have_no_score_and_every_topic_is_listed(
    client, db, student, room
) -> None:
    course, (parens, transpose, _) = room
    graded(db, course["id"], student, 2, "correct", transpose)
    graded(db, course["id"], student, 1, "incorrect", transpose)

    body = progress(client, student, course["id"]).json()

    assert [t["topic_name"] for t in body["topics"]] == [
        "Paréntesis",
        "Transponer",
        "Despejar",
    ]
    few = topic_of(body, "Transponer")
    assert (few["level"], few["score"]) == ("insufficient", None)
    none = topic_of(body, "Paréntesis")
    assert (none["level"], none["score"], none["last_activity_at"]) == (
        "not_started",
        None,
        None,
    )


def test_history_has_eight_weeks_oldest_first(client, db, student, room) -> None:
    course, (parens, *_) = room
    for days in (22, 21, 20):
        graded(db, course["id"], student, days, "incorrect", parens)
    quiz(db, course["id"], student, parens, [True, True, True], days_ago=0)

    history = topic_of(progress(client, student, course["id"]).json(), "Paréntesis")[
        "history"
    ]

    assert len(history) == 8
    starts = [datetime.fromisoformat(w["week_start"]).date() for w in history]
    assert starts == sorted(starts) and all(d.weekday() == 0 for d in starts)
    assert history[0]["score"] is None
    assert history[-1]["score"] == 0.5
    # Three weeks ago only the three mistakes counted.
    three_weeks_ago = (datetime.now(UTC) - timedelta(days=20)).date()
    week = three_weeks_ago - timedelta(days=three_weeks_ago.weekday())
    scores = {
        datetime.fromisoformat(w["week_start"]).date(): w["score"] for w in history
    }
    assert scores[week] in (None, 0.0)


def test_the_most_frequent_mistakes_link_to_the_latest_one(
    client, db, student, room
) -> None:
    course, (parens, *_) = room
    graded(db, course["id"], student, 6, "incorrect", parens, "procedural")
    latest = graded(db, course["id"], student, 2, "incorrect", parens, "procedural")
    graded(db, course["id"], student, 4, "partially_correct", parens, "conceptual")

    errors = topic_of(progress(client, student, course["id"]).json(), "Paréntesis")[
        "top_errors"
    ]

    assert errors[0] == {
        "error_type": "procedural",
        "count": 2,
        "latest_submission_id": str(latest),
        "correct_since": 0,
        "overcome": False,
    }
    assert [(e["error_type"], e["count"]) for e in errors[1:]] == [("conceptual", 1)]


def test_graded_work_without_topic_is_apart_and_not_assessed_never_counts(
    client, db, student, room
) -> None:
    course, (parens, *_) = room
    for days in (3, 2, 1):
        graded(db, course["id"], student, days, "correct")
    graded(db, course["id"], student, 1, "not_assessed", parens)

    body = progress(client, student, course["id"]).json()

    assert body["unassigned"]["topic_id"] is None
    assert body["unassigned"]["basis"]["exercises_total"] == 3
    assert body["unassigned"]["level"] == "mastered"
    assert topic_of(body, "Paréntesis")["level"] == "not_started"


def test_without_activity_everything_is_not_started(client, student, room) -> None:
    course, _ = room

    body = progress(client, student, course["id"]).json()

    assert {t["level"] for t in body["topics"]} == {"not_started"}
    assert body["updated_at"] is None
    assert body["unassigned"] is None
    assert body["quizzes_completed"] == 0


def test_the_teacher_sees_the_same_progress(client, db, teacher, student, room) -> None:
    course, (parens, *_) = room
    graded(db, course["id"], student, 3, "incorrect", parens)
    quiz(db, course["id"], student, parens, [True, True], days_ago=1)

    mine = progress(client, student, course["id"])
    theirs = progress(client, teacher, course["id"], student)

    assert theirs.status_code == 200, theirs.text
    assert theirs.json() == mine.json()


def test_progress_is_only_for_the_owned_course_and_its_students(
    client, other_teacher, teacher, student, other_student, room
) -> None:
    course, _ = room

    assert progress(client, other_teacher, course["id"], student).status_code == 404
    assert progress(client, teacher, course["id"], other_student).status_code == 404
    assert progress(client, other_student, course["id"]).status_code == 404


def test_weekly_activity_counts_completed_quizzes(
    client, db, teacher, student, room
) -> None:
    course, (parens, *_) = room
    quiz(db, course["id"], student, parens, [True], days_ago=1)
    quiz(db, course["id"], student, parens, [False], days_ago=1)

    weeks = risk_of(client, teacher, course["id"], student).json()["weekly_activity"]

    assert sum(w["quizzes"] for w in weeks) == 2
