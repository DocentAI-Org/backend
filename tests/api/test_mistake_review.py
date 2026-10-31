"""US2 (spec 005) — a targeted review of a repeated mistake, from the material."""

from sqlalchemy import select

from app.models import InteractionLog
from tests.api.test_repeated_mistakes import mistakes, repeated_room
from tests.api.test_us7_exercises import MISTAKE, submit

REVIEW = {
    "explanation": "Al quitar el paréntesis, el factor multiplica a cada término.",
    "worked_example": "3(x + 2) = 3x + 6, porque 3 · x = 3x y 3 · 2 = 6.",
    "practice": ["Quita los paréntesis: 4(x - 1) = 8", "Resuelve 2(x + 5) = 14"],
    "cited": ["F1"],
}


def review_path(course_id: str, submission_id: str, role: str = "student") -> str:
    return f"/v1/{role}/courses/{course_id}/submissions/{submission_id}/review"


def ask_review(client, user, course_id: str, submission_id: str):
    return client.post(review_path(course_id, submission_id), headers=user.headers)


def allowance_used(client, student) -> int:
    return client.get("/v1/student/allowance", headers=student.headers).json()["used"]


def review_logs(db, course_id: str) -> list[InteractionLog]:
    return list(
        db.scalars(
            select(InteractionLog).where(
                InteractionLog.course_id == course_id, InteractionLog.kind == "review"
            )
        )
    )


def test_a_repeated_mistake_gets_a_grounded_review_that_counts(
    client, db, llm, teacher, student
) -> None:
    room, made = repeated_room(client, llm, teacher, student)
    llm.reply = REVIEW

    response = ask_review(client, student, room.course_id, made[2]["id"])

    assert response.status_code == 201, response.text
    review = response.json()
    assert review["submission_id"] == made[2]["id"]
    assert review["kind"] == "answer"
    assert (review["error_type"], review["topic_name"]) == ("procedural", "Paréntesis")
    assert review["explanation"] == REVIEW["explanation"]
    assert review["worked_example"] == REVIEW["worked_example"]
    assert review["practice"] == REVIEW["practice"]
    assert [c["document_name"] for c in review["citations"]] == ["ecuaciones.md"]
    assert allowance_used(client, student) == 4
    [log] = review_logs(db, room.course_id)
    assert (log.outcome, log.model) == ("answer", "fake-model")

    system, messages = llm.chat_calls[-1]
    content = messages[-1]["content"]
    assert "Error de procedimiento" in content and "Paréntesis" in content
    assert student.display_name not in content and student.display_name not in system


def test_asking_again_returns_the_same_review_for_free(
    client, llm, teacher, student
) -> None:
    room, made = repeated_room(client, llm, teacher, student)
    llm.reply = REVIEW
    first = ask_review(client, student, room.course_id, made[2]["id"]).json()
    calls = len(llm.chat_calls)

    again = ask_review(client, student, room.course_id, made[2]["id"])
    read = client.get(
        review_path(room.course_id, made[2]["id"]), headers=student.headers
    )

    assert again.status_code == 200
    assert again.json() == first == read.json()
    assert len(llm.chat_calls) == calls
    assert allowance_used(client, student) == 4


def test_no_review_yet_is_404(client, llm, teacher, student) -> None:
    room, made = repeated_room(client, llm, teacher, student)

    read = client.get(
        review_path(room.course_id, made[2]["id"]), headers=student.headers
    )

    assert read.status_code == 404


def test_an_unusable_reply_is_stored_as_not_covered(
    client, llm, teacher, student
) -> None:
    room, made = repeated_room(client, llm, teacher, student)
    llm.reply = REVIEW | {"cited": ["F9"]}

    review = ask_review(client, student, room.course_id, made[2]["id"]).json()

    assert review["kind"] == "no_source"
    assert review["practice"] == []
    assert review["worked_example"] is None
    assert review["citations"] == []
    assert "material" in review["explanation"].lower()


def test_hints_only_courses_review_without_solving(
    client, llm, teacher, student
) -> None:
    room, made = repeated_room(client, llm, teacher, student)
    client.put(
        f"/v1/teacher/courses/{room.course_id}/tutor-settings",
        headers=teacher.headers,
        json={"level": "basic", "tone": "friendly", "solution_policy": "hints_only"},
    )
    llm.reply = REVIEW

    ask_review(client, student, room.course_id, made[2]["id"])

    system, _ = llm.chat_calls[-1]
    assert "no resuelvas el ejercicio del estudiante" in system.lower()
    assert "no des la solución de los ejercicios de práctica" in system.lower()


def test_without_a_repeated_mistake_there_is_no_review(
    client, llm, teacher, student
) -> None:
    room, made = repeated_room(client, llm, teacher, student, count=2)

    response = ask_review(client, student, room.course_id, made[1]["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_repeated_mistake"


def test_provider_failure_stores_nothing_and_releases_the_allowance(
    client, db, llm, teacher, student
) -> None:
    room, made = repeated_room(client, llm, teacher, student)
    llm.fail_chat = True

    response = ask_review(client, student, room.course_id, made[2]["id"])

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "tutor_unavailable"
    assert allowance_used(client, student) == 3
    assert (
        client.get(
            review_path(room.course_id, made[2]["id"]), headers=student.headers
        ).status_code
        == 404
    )
    assert [log.outcome for log in review_logs(db, room.course_id)] == ["error"]


def test_the_daily_limit_applies(client, llm, teacher, student) -> None:
    room, made = repeated_room(client, llm, teacher, student)
    llm.reply = MISTAKE
    for _ in range(2):
        assert submit(client, student, room.course_id).status_code == 201
    llm.reply = REVIEW

    response = ask_review(client, student, room.course_id, made[2]["id"])

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "daily_limit_reached"


def test_the_teacher_reads_the_review_and_others_cannot(
    client, llm, teacher, other_teacher, student, other_student
) -> None:
    room, made = repeated_room(client, llm, teacher, student)
    llm.reply = REVIEW
    review = ask_review(client, student, room.course_id, made[2]["id"]).json()
    path = review_path(room.course_id, made[2]["id"], "teacher")

    assert client.get(path, headers=teacher.headers).json() == review
    assert client.get(path, headers=other_teacher.headers).status_code == 404
    assert (
        ask_review(client, other_student, room.course_id, made[2]["id"]).status_code
        == 404
    )


def test_a_pattern_without_topic_reviews_too(client, llm, teacher, student) -> None:
    room, _ = repeated_room(client, llm, teacher, student, count=0)
    made = mistakes(client, llm, student, room.course_id, 3, MISTAKE | {"topic": None})
    llm.reply = REVIEW

    review = ask_review(client, student, room.course_id, made[2]["id"]).json()

    assert (review["kind"], review["topic_name"]) == ("answer", None)
