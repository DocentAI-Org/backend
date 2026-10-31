"""US1–US2 (spec 013) — explanations adapted to recurring mistakes, with their basis."""

from sqlalchemy import text

from tests.api.helpers import (
    COVERED_QUESTION,
    UNCOVERED_QUESTION,
    ask,
    classroom,
    open_conversation,
)
from tests.api.test_progress import graded
from tests.api.test_us2_courses import create_course
from tests.api.test_us7_exercises import MISTAKE, UNCOVERED, submit

NOTE = "procedimiento"  # in the label of `procedural`, which the note names


def mistakes(db, course_id: str, student, days_ago: float, count: int, kind: str):
    for _ in range(count):
        graded(db, course_id, student, days_ago, "incorrect", None, kind)
    db.commit()


def chat(client, student, course_id: str, text: str = COVERED_QUESTION) -> dict:
    conversation = open_conversation(client, student, course_id)
    response = ask(client, student, course_id, conversation["id"], text)
    assert response.status_code == 201, response.text
    return {"conversation": conversation, **response.json()}


def test_recurring_mistakes_adapt_the_chat_answer(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    mistakes(db, room.course_id, student, 3, 2, "execution")
    mistakes(db, room.course_id, student, 2, 3, "procedural")

    reply = chat(client, student, room.course_id)["tutor_message"]

    days = 30  # the study's default repeated-mistake window (spec 015)
    assert reply["adaptation"] == {
        "error_type": "procedural",
        "count": 3,
        "window_days": days,
    }
    system, messages = llm.chat_calls[-1]
    assert NOTE in system.lower()
    sent = system + "".join(m["content"] for m in messages)
    for personal in (str(student.id), student.display_name):
        assert personal not in sent


def test_recurring_mistakes_adapt_the_exercise_feedback(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    mistakes(db, room.course_id, student, 1, 3, "conceptual")
    llm.reply = MISTAKE

    feedback = submit(client, student, room.course_id).json()

    assert feedback["adaptation"]["error_type"] == "conceptual"
    assert feedback["adaptation"]["count"] == 3
    assert "conceptual" in llm.chat_calls[-1][0].lower()


def test_no_adaptation_below_the_threshold_outside_the_window_or_course(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    other = create_course(client, teacher)
    days = 30  # the study's default repeated-mistake window (spec 015)
    mistakes(db, room.course_id, student, 1, 2, "procedural")
    mistakes(db, room.course_id, student, days + 1, 3, "procedural")
    mistakes(db, other["id"], student, 1, 3, "procedural")
    llm.reply = MISTAKE

    assert chat(client, student, room.course_id)["tutor_message"]["adaptation"] is None
    assert submit(client, student, room.course_id).json()["adaptation"] is None
    assert NOTE not in llm.chat_calls[-1][0].lower()


def test_no_adaptation_without_an_answer_from_the_material(
    client, db, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    mistakes(db, room.course_id, student, 1, 3, "procedural")

    uncovered = chat(client, student, room.course_id, UNCOVERED_QUESTION)
    assert uncovered["tutor_message"]["kind"] == "no_source"
    assert uncovered["tutor_message"]["adaptation"] is None
    feedback = submit(client, student, room.course_id, UNCOVERED).json()
    assert feedback["verdict"] == "not_assessed"
    assert feedback["adaptation"] is None


def test_the_teacher_sees_the_same_basis(client, db, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    mistakes(db, room.course_id, student, 1, 3, "procedural")
    exchange = chat(client, student, room.course_id)
    llm.reply = MISTAKE
    submission = submit(client, student, room.course_id).json()
    base = f"/v1/teacher/courses/{room.course_id}"

    conversation = client.get(
        f"{base}/conversations/{exchange['conversation']['id']}",
        headers=teacher.headers,
    ).json()
    reviewed = client.get(
        f"{base}/submissions/{submission['id']}", headers=teacher.headers
    ).json()

    tutor = [m for m in conversation["messages"] if m["author"] == "tutor"]
    assert tutor[-1]["adaptation"] == exchange["tutor_message"]["adaptation"]
    assert reviewed["adaptation"] == submission["adaptation"]
    assert reviewed["adaptation"] is not None


def test_the_note_comes_before_the_reply_format(
    client, db, llm, teacher, student
) -> None:
    # After the format, a small model forgot "cited" and every adapted exercise came
    # back not_assessed (found in the end-to-end review).
    room = classroom(client, teacher, student)
    mistakes(db, room.course_id, student, 1, 3, "procedural")
    chat(client, student, room.course_id)
    llm.reply = MISTAKE
    submit(client, student, room.course_id)

    for system, _ in llm.chat_calls:
        note = system.lower().index(NOTE)
        assert note < system.index("Devuelve solo un objeto JSON"), system[-400:]


def test_without_adaptation_the_column_is_sql_null(client, db, llm, teacher, student):
    room = classroom(client, teacher, student)
    llm.reply = MISTAKE
    submitted = submit(client, student, room.course_id).json()
    chat(client, student, room.course_id)

    rows = db.execute(
        text(
            "select (select adaptation is null from exercise_submissions"
            " where id = :s), bool_and(adaptation is null) from messages m"
            " join conversations c on c.id = m.conversation_id where c.course_id = :c"
        ),
        {"s": submitted["id"], "c": room.course_id},
    ).one()
    assert rows == (True, True)
