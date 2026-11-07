"""US1–US2 (spec 017) — the admin erases a student and everything linked to them."""

import uuid

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import InteractionLog, Message, TeacherFlag
from app.models import TestAnswer as Answer
from app.services.interactions import student_ref
from tests.api.helpers import COVERED_QUESTION, ask, classroom, open_conversation
from tests.api.test_course_tags import new_tag, tag_course
from tests.api.test_course_test_setup import add_question, set_phase
from tests.api.test_progress import quiz
from tests.api.test_us6_topics import create_topic
from tests.api.test_us7_exercises import MISTAKE, submit

# Every column of a public table that references profiles(id) and cascades.
LINKED_COLUMNS = text(
    """
    select src.relname, att.attname
    from pg_constraint con
    join pg_class src on src.oid = con.conrelid
    join pg_namespace ns on ns.oid = src.relnamespace
    join pg_attribute att on att.attrelid = con.conrelid and att.attnum = con.conkey[1]
    where con.contype = 'f'
      and con.confrelid = 'public.profiles'::regclass
      and con.confdeltype = 'c'
      and ns.nspname = 'public'
    """
)


def erase(client, user, student_id) -> object:
    return client.delete(f"/v1/admin/students/{student_id}", headers=user.headers)


def linked_rows(db, user_id) -> dict[str, int]:
    counts = {}
    for table, column in db.execute(LINKED_COLUMNS).all():
        counts[f"{table}.{column}"] = db.scalar(
            text(f'select count(*) from public."{table}" where "{column}" = :id'),
            {"id": user_id},
        )
    counts["profiles.id"] = db.scalar(
        text("select count(*) from public.profiles where id = :id"), {"id": user_id}
    )
    counts["auth.users.id"] = db.scalar(
        text("select count(*) from auth.users where id = :id"), {"id": user_id}
    )
    return counts


def log_count(db, user_id) -> int:
    ref = student_ref(get_settings(), user_id)
    return db.scalar(
        select(func.count(InteractionLog.id)).where(InteractionLog.student_ref == ref)
    )


@pytest.fixture
def erasable(client, db, llm, teacher, student, other_student):
    """Two students with activity in the same course; the first will be erased."""
    room = classroom(client, teacher, student)
    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    client.post("/v1/student/consent", headers=other_student.headers)
    client.post(
        f"/v1/student/courses/{room.course_id}/disclosure",
        headers=other_student.headers,
    )
    topic = create_topic(client, teacher, room.course_id, "Signos").json()
    question = add_question(client, teacher, room.course_id, topic["id"]).json()
    assert set_phase(client, teacher, room.course_id, "pre", "open").status_code == 200

    conversations = {}
    for user in (student, other_student):
        conversation = open_conversation(client, user, room.course_id)
        exchange = ask(
            client, user, room.course_id, conversation["id"], COVERED_QUESTION
        )
        assert exchange.status_code == 201, exchange.text
        llm.reply = MISTAKE
        submission = submit(client, user, room.course_id)
        assert submission.status_code == 201, submission.text
        base = f"/v1/teacher/courses/{room.course_id}"
        flag = client.put(
            f"{base}/messages/{exchange.json()['tutor_message']['id']}/flag",
            headers=teacher.headers,
            json={"category": "incorrect", "correction": "Divide entre 2."},
        )
        assert flag.status_code == 200, flag.text
        quiz(db, room.course_id, user, topic, [True, False], days_ago=1)
        taken = client.post(
            f"/v1/student/courses/{room.course_id}/test/pre",
            headers=user.headers,
            json={"answers": [{"question_id": question["id"], "choice": 0}]},
        )
        assert taken.status_code == 201, taken.text
        tag = new_tag(client, user, "Mío").json()
        assert tag_course(client, user, tag["id"], room.course_id).status_code < 300
        assert (
            client.put(
                f"/v1/me/favorite-courses/{room.course_id}", headers=user.headers
            ).status_code
            < 300
        )
        conversations[user.id] = conversation["id"]
    db.commit()
    return room, conversations


def test_the_admin_erases_every_row_linked_to_the_student(
    client, db, admin, student, erasable
) -> None:
    _, conversations = erasable
    before = linked_rows(db, student.id)
    assert before["enrolments.student_id"] == 1
    assert before["consent_events.student_id"] >= 1
    assert before["conversations.student_id"] == 1
    assert before["exercise_submissions.student_id"] == 1
    assert before["learning_record_entries.student_id"] == 1
    assert before["quizzes.student_id"] == 1
    assert before["test_attempts.student_id"] == 1
    assert before["daily_usage.student_id"] == 1
    assert before["course_favorites.user_id"] == 1
    assert before["course_tags.user_id"] == 1
    logs = log_count(db, student.id)
    assert logs >= 2  # the chat answer and the exercise feedback

    response = erase(client, admin, student.id)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "student_id": str(student.id),
        "courses": 1,
        "conversations": 1,
        "messages": 2,
        "exercise_submissions": 1,
        "quizzes": 1,
        "test_attempts": 1,
        "interaction_logs": logs,
    }
    db.expire_all()
    after = linked_rows(db, student.id)
    assert set(after.values()) == {0}, after
    assert log_count(db, student.id) == 0
    conversation_id = conversations[student.id]
    assert (
        db.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation_id
            )
        )
        == 0
    )


def test_other_students_are_untouched(
    client, db, admin, student, other_student, erasable
) -> None:
    _, conversations = erasable
    before = linked_rows(db, other_student.id)
    logs = log_count(db, other_student.id)
    flags = db.scalar(select(func.count(TeacherFlag.id)))
    answers = db.scalar(select(func.count()).select_from(Answer))

    assert erase(client, admin, student.id).status_code == 200

    db.expire_all()
    assert linked_rows(db, other_student.id) == before
    assert log_count(db, other_student.id) == logs
    # The erased student's flag and test answer went with them, no one else's.
    assert db.scalar(select(func.count(TeacherFlag.id))) == flags - 1
    assert db.scalar(select(func.count()).select_from(Answer)) == answers - 1
    other_conversation = conversations[other_student.id]
    assert (
        db.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == other_conversation
            )
        )
        == 2
    )


def test_an_erased_student_token_no_longer_works(
    client, admin, student, erasable
) -> None:
    assert erase(client, admin, student.id).status_code == 200

    assert client.get("/v1/me", headers=student.headers).status_code == 401


def test_a_second_erasure_is_404(client, admin, student, erasable) -> None:
    assert erase(client, admin, student.id).status_code == 200

    response = erase(client, admin, student.id)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert erase(client, admin, uuid.uuid4()).status_code == 404


def test_teachers_and_admins_cannot_be_erased(
    client, db, admin, teacher, erasable
) -> None:
    for user_id in (teacher.id, admin.id):
        before = linked_rows(db, user_id)

        response = erase(client, admin, user_id)

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "not_a_student"
        db.expire_all()
        assert linked_rows(db, user_id) == before


def test_only_the_admin_can_erase(
    client, teacher, student, other_student, erasable
) -> None:
    assert erase(client, teacher, student.id).status_code == 403
    assert erase(client, other_student, student.id).status_code == 403
    assert erase(client, student, student.id).status_code == 403


def test_an_auth_failure_deletes_nothing(
    client, db, admin, student, auth_admin, erasable
) -> None:
    before = linked_rows(db, student.id)
    logs = log_count(db, student.id)
    auth_admin.fail_with = ApiError(
        503, "auth_unavailable", "The authentication service is unreachable."
    )

    response = erase(client, admin, student.id)

    assert response.status_code == 503
    db.expire_all()
    assert linked_rows(db, student.id) == before
    assert log_count(db, student.id) == logs
