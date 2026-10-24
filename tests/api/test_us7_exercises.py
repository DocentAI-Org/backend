"""US7 — exercise submission (contract stub) and learning record (S4)."""

from sqlalchemy import select

from app.models import InteractionLog
from tests.api.helpers import classroom
from tests.api.test_us6_topics import create_topic

EXERCISE = {
    "problem_statement": "Resuelve 2(x - 3) = 4x + 2",
    "worked_answer": "2x - 3 = 4x + 2\n-2x = 5\nx = -5/2",
}


def submit(client, student, course_id: str, payload: dict | None = None):
    return client.post(
        f"/v1/student/courses/{course_id}/submissions",
        headers=student.headers,
        json=payload or EXERCISE,
    )


def test_submission_returns_stub_feedback_and_saves_learning_record(
    client, db, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    create_topic(client, teacher, room.course_id, "Paréntesis")

    response = submit(client, student, room.course_id)

    assert response.status_code == 201, response.text
    feedback = response.json()
    assert feedback["is_stub"] is True
    assert feedback["verdict"] == "incorrect"
    assert feedback["mistake_location"] == "Paso 1"
    assert feedback["error_type"] == "placeholder"
    assert feedback["topic_name"] == "Paréntesis"
    assert feedback["saved_to_record"] is True
    assert feedback["explanation_kind"] in {"answer", "no_source"}
    assert feedback["correction"] is None

    record = client.get(
        f"/v1/student/courses/{room.course_id}/learning-record",
        headers=student.headers,
    ).json()
    assert record["total"] == 1
    entry = record["items"][0]
    assert entry["submission_id"] == feedback["id"]
    assert entry["error_type"] == "placeholder"
    assert entry["topic_deleted"] is False

    log = db.scalars(
        select(InteractionLog).where(InteractionLog.course_id == room.course_id)
    ).one()
    assert (log.kind, log.outcome, log.model) == ("exercise", "stub", None)


def test_submission_counts_toward_the_allowance(client, teacher, student) -> None:
    room = classroom(client, teacher, student)

    submit(client, student, room.course_id)

    allowance = client.get("/v1/student/allowance", headers=student.headers).json()
    assert allowance["used"] == 1


def test_submission_requires_disclosure_and_valid_input(
    client, teacher, student
) -> None:
    room = classroom(client, teacher, student, acknowledge=False)
    blocked = submit(client, student, room.course_id)
    assert blocked.json()["error"]["code"] == "disclosure_not_acknowledged"

    client.post(
        f"/v1/student/courses/{room.course_id}/disclosure", headers=student.headers
    )
    empty = submit(client, student, room.course_id, {**EXERCISE, "worked_answer": ""})
    assert empty.status_code == 422


def test_deleted_topic_keeps_its_name_in_the_learning_record(
    client, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    topic = create_topic(client, teacher, room.course_id, "Paréntesis").json()
    submit(client, student, room.course_id)

    client.delete(
        f"/v1/teacher/courses/{room.course_id}/topics/{topic['id']}",
        headers=teacher.headers,
    )

    entry = client.get(
        f"/v1/student/courses/{room.course_id}/learning-record",
        headers=student.headers,
    ).json()["items"][0]
    assert entry["topic_id"] is None
    assert entry["topic_name"] == "Paréntesis"
    assert entry["topic_deleted"] is True


def test_learning_record_is_visible_only_to_student_and_their_teacher(
    client, teacher, other_teacher, student, other_student
) -> None:
    room = classroom(client, teacher, student)
    submit(client, student, room.course_id)
    teacher_path = (
        f"/v1/teacher/courses/{room.course_id}/students/{student.id}/learning-record"
    )

    as_teacher = client.get(teacher_path, headers=teacher.headers)
    assert as_teacher.status_code == 200
    assert as_teacher.json()["total"] == 1

    assert client.get(teacher_path, headers=other_teacher.headers).status_code == 404
    other_view = client.get(
        f"/v1/student/courses/{room.course_id}/learning-record",
        headers=other_student.headers,
    )
    assert other_view.status_code == 404


def test_student_lists_and_reads_own_submissions(
    client, teacher, student, other_student
) -> None:
    room = classroom(client, teacher, student)
    created = submit(client, student, room.course_id).json()
    base = f"/v1/student/courses/{room.course_id}/submissions"

    listed = client.get(base, headers=student.headers).json()
    assert [s["id"] for s in listed["items"]] == [created["id"]]
    detail = client.get(f"{base}/{created['id']}", headers=student.headers)
    assert detail.json()["problem_statement"] == EXERCISE["problem_statement"]

    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    assert (
        client.get(f"{base}/{created['id']}", headers=other_student.headers).status_code
        == 404
    )


def test_stub_endpoint_is_marked_in_the_contract(client) -> None:
    operation = client.get("/openapi.json").json()["paths"][
        "/v1/student/courses/{course_id}/submissions"
    ]["post"]

    assert operation["x-stub"] is True
