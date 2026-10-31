"""US3 (spec 006) — the student takes an adaptive quiz with immediate feedback."""

from tests.api.helpers import classroom
from tests.api.test_quiz_questions import (
    approved_questions,
    draft,
    edit,
    generate,
    topic_with_material,
)
from tests.api.test_us6_topics import create_topic

# Two questions per level, so the quiz can move up and down.
LEVELS = {
    "questions": [
        draft(f"Nivel {level}, pregunta {n}", difficulty=level)
        for level in (1, 2, 3)
        for n in (1, 2)
    ]
}
# Every draft's right answer is "2x - 6"; generation moves it to different positions,
# so answers are given by text: RIGHT and WRONG pick the option shown to the student.
RIGHT, WRONG = True, False
RIGHT_TEXT, WRONG_TEXT = "2x - 6", "2x - 3"


def quizzes_path(course_id: str) -> str:
    return f"/v1/student/courses/{course_id}/quizzes"


def start(client, student, course_id: str, topic_id: str | None = None):
    return client.post(
        quizzes_path(course_id),
        headers=student.headers,
        json={} if topic_id is None else {"topic_id": topic_id},
    )


def answer(client, student, course_id: str, quiz: dict, choice, question_id=None):
    if isinstance(choice, bool):
        options = quiz["current"]["options"] if quiz["current"] else []
        text = RIGHT_TEXT if choice else WRONG_TEXT
        choice = options.index(text) if text in options else 0
    return client.post(
        f"{quizzes_path(course_id)}/{quiz['id']}/answers",
        headers=student.headers,
        json={"question_id": question_id or quiz["current"]["id"], "choice": choice},
    )


def quiz_room(client, llm, teacher, student, replies=LEVELS):
    room, topic, made = approved_questions(client, llm, teacher, student, replies)
    return room, topic, made


def test_a_quiz_starts_at_the_middle_level_without_answers(
    client, llm, teacher, student
) -> None:
    room, topic, _ = quiz_room(client, llm, teacher, student)

    response = start(client, student, room.course_id, topic["id"])

    assert response.status_code == 201, response.text
    quiz = response.json()
    assert quiz["status"] == "in_progress"
    assert quiz["topic_name"] == "Paréntesis"
    assert quiz["question_count"] == 5
    assert (quiz["answered_count"], quiz["level"]) == (0, 2)
    current = quiz["current"]
    assert current["position"] == 1
    assert current["difficulty"] == 2
    assert current["statement"].startswith("Nivel 2")
    assert "correct_option" not in current and "explanation" not in current
    assert quiz["summary"] is None


def test_fewer_approved_questions_make_a_shorter_quiz(
    client, llm, teacher, student
) -> None:
    room, _, _ = quiz_room(
        client, llm, teacher, student, {"questions": [draft("Única pregunta")]}
    )

    quiz = start(client, student, room.course_id).json()

    assert quiz["question_count"] == 1
    assert quiz["topic_id"] is None


def test_only_approved_questions_reach_students(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    topic = topic_with_material(client, teacher, room.course_id, room.document["id"])
    llm.reply = {"questions": [draft("Pendiente"), draft("Rechazada")]}
    made = generate(client, teacher, room.course_id, topic["id"]).json()["questions"]
    edit(client, teacher, room.course_id, made[1]["id"], status="rejected")

    response = start(client, student, room.course_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_questions"


def test_a_topic_without_approved_questions_has_no_quiz(
    client, llm, teacher, student
) -> None:
    room, _, _ = quiz_room(client, llm, teacher, student)
    other = create_topic(client, teacher, room.course_id, "Transponer").json()

    response = start(client, student, room.course_id, other["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_questions"


def test_each_answer_gets_immediate_feedback(client, llm, teacher, student) -> None:
    room, _, _ = quiz_room(client, llm, teacher, student)
    quiz = start(client, student, room.course_id).json()

    response = answer(client, student, room.course_id, quiz, WRONG)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["correct"] is False
    assert quiz["current"]["options"][result["correct_option"]] == RIGHT_TEXT
    assert result["explanation"] == "El 2 multiplica a cada término de dentro."
    assert [c["document_name"] for c in result["citations"]] == ["ecuaciones.md"]
    assert result["difficulty_change"] is None
    assert result["quiz"]["answered_count"] == 1
    assert result["quiz"]["current"]["position"] == 2
    assert result["quiz"]["current"]["id"] != quiz["current"]["id"]


def test_only_the_current_question_can_be_answered(
    client, llm, teacher, student
) -> None:
    room, _, made = quiz_room(client, llm, teacher, student)
    quiz = start(client, student, room.course_id).json()
    other = next(q["id"] for q in made if q["id"] != quiz["current"]["id"])

    wrong_question = answer(client, student, room.course_id, quiz, RIGHT, other)
    first = answer(client, student, room.course_id, quiz, RIGHT)
    twice = answer(client, student, room.course_id, quiz, RIGHT)
    out_of_range = answer(
        client, student, room.course_id, first.json()["quiz"], choice=4
    )

    assert wrong_question.status_code == twice.status_code == 409
    assert twice.json()["error"]["code"] == "not_current_question"
    assert out_of_range.status_code == 422


def test_two_right_answers_raise_the_level(client, llm, teacher, student) -> None:
    room, _, _ = quiz_room(client, llm, teacher, student)
    quiz = start(client, student, room.course_id).json()

    first = answer(client, student, room.course_id, quiz, RIGHT).json()
    second = answer(client, student, room.course_id, first["quiz"], RIGHT).json()

    assert first["difficulty_change"] is None
    assert second["difficulty_change"] == {
        "from_level": 2,
        "to_level": 3,
        "reason": "correct_streak",
        "streak": 2,
    }
    assert second["quiz"]["level"] == 3
    assert second["quiz"]["current"]["difficulty"] == 3


def test_two_wrong_answers_lower_the_level(client, llm, teacher, student) -> None:
    room, _, _ = quiz_room(client, llm, teacher, student)
    quiz = start(client, student, room.course_id).json()

    first = answer(client, student, room.course_id, quiz, WRONG).json()
    second = answer(client, student, room.course_id, first["quiz"], WRONG).json()

    assert second["difficulty_change"]["reason"] == "wrong_streak"
    assert (second["quiz"]["level"], second["quiz"]["current"]["difficulty"]) == (1, 1)


def test_the_nearest_level_is_used_when_one_runs_out(
    client, llm, teacher, student
) -> None:
    room, _, _ = quiz_room(
        client,
        llm,
        teacher,
        student,
        {"questions": [draft("Media", difficulty=2), draft("Fácil", difficulty=1)]},
    )
    quiz = start(client, student, room.course_id).json()

    after = answer(client, student, room.course_id, quiz, RIGHT).json()

    assert after["quiz"]["level"] == 2
    assert after["quiz"]["current"]["statement"] == "Fácil"


def test_the_last_answer_completes_the_quiz_with_a_summary(
    client, llm, teacher, student
) -> None:
    room, topic, _ = quiz_room(client, llm, teacher, student)
    quiz = start(client, student, room.course_id).json()
    for choice in (RIGHT, RIGHT, WRONG, RIGHT, WRONG):
        result = answer(client, student, room.course_id, quiz, choice).json()
        quiz = result["quiz"]

    assert quiz["status"] == "completed"
    assert quiz["current"] is None
    assert quiz["completed_at"] is not None
    assert quiz["summary"] == {
        "score": 3,
        "total": 5,
        "final_level": quiz["level"],
        "by_topic": [
            {
                "topic_id": topic["id"],
                "topic_name": "Paréntesis",
                "correct": 3,
                "total": 5,
            }
        ],
    }
    again = answer(client, student, room.course_id, quiz, RIGHT, quiz["id"])
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "quiz_completed"

    detail = client.get(
        f"{quizzes_path(room.course_id)}/{quiz['id']}", headers=student.headers
    ).json()
    assert [item["correct"] for item in detail["items"]] == [
        True,
        True,
        False,
        True,
        False,
    ]
    first_item = detail["items"][0]
    assert first_item["options"][first_item["correct_option"]] == RIGHT_TEXT
    listed = client.get(quizzes_path(room.course_id), headers=student.headers).json()
    assert [q["id"] for q in listed["items"]] == [quiz["id"]]


def test_unseen_questions_come_first(client, llm, teacher, student) -> None:
    room, _, _ = quiz_room(
        client,
        llm,
        teacher,
        student,
        {"questions": [draft("Primera", difficulty=2), draft("Segunda", difficulty=2)]},
    )
    first = start(client, student, room.course_id).json()
    answer(client, student, room.course_id, first, RIGHT)

    second = start(client, student, room.course_id).json()

    assert first["current"]["statement"] != second["current"]["statement"]


def test_teacher_edits_do_not_change_a_started_quiz(
    client, llm, teacher, student
) -> None:
    room, _, _ = quiz_room(
        client, llm, teacher, student, {"questions": [draft("Original")]}
    )
    quiz = start(client, student, room.course_id).json()
    question_id = quiz["current"]["id"]
    edit(
        client,
        teacher,
        room.course_id,
        question_id,
        statement="Cambiada",
        correct_option=2,
        status="rejected",
    )

    result = answer(client, student, room.course_id, quiz, RIGHT).json()

    assert result["correct"] is True
    detail = client.get(
        f"{quizzes_path(room.course_id)}/{quiz['id']}", headers=student.headers
    ).json()
    assert detail["items"][0]["statement"] == "Original"


def test_teachers_see_how_questions_were_answered(
    client, llm, teacher, student
) -> None:
    room, _, _ = quiz_room(
        client, llm, teacher, student, {"questions": [draft("Única pregunta")]}
    )
    for choice in (RIGHT, WRONG):
        quiz = start(client, student, room.course_id).json()
        answer(client, student, room.course_id, quiz, choice)

    [question] = client.get(
        f"/v1/teacher/courses/{room.course_id}/questions", headers=teacher.headers
    ).json()["items"]

    assert (question["answered_count"], question["correct_rate"]) == (2, 0.5)


def test_quizzes_need_consent_and_are_private(
    client, llm, teacher, student, other_student
) -> None:
    room, _, _ = quiz_room(client, llm, teacher, student)
    quiz = start(client, student, room.course_id).json()
    client.delete("/v1/student/consent", headers=student.headers)

    blocked = start(client, student, room.course_id)
    blocked_answer = answer(client, student, room.course_id, quiz, RIGHT)
    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    foreign = client.get(
        f"{quizzes_path(room.course_id)}/{quiz['id']}", headers=other_student.headers
    )

    assert blocked.status_code == blocked_answer.status_code == 409
    assert blocked.json()["error"]["code"] == "consent_required"
    assert foreign.status_code == 404
    # Revoking keeps read access to the student's own data.
    own = client.get(
        f"{quizzes_path(room.course_id)}/{quiz['id']}", headers=student.headers
    )
    assert own.status_code == 200
