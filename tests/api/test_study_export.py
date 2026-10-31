"""US1–US2 (spec 011) — study export: consenting students only, no personal data."""

import csv
import io
import zipfile

import pytest

from app.core.config import get_settings
from app.services.interactions import student_ref
from tests.api.helpers import (
    COVERED_QUESTION,
    ask,
    classroom,
    open_conversation,
)
from tests.api.test_course_test_setup import add_question, set_phase
from tests.api.test_progress import graded, quiz
from tests.api.test_us2_courses import create_course
from tests.api.test_us6_topics import create_topic
from tests.api.test_us7_exercises import EXERCISE, MISTAKE, submit

COLUMNS = {
    "students.csv": "study_ref,course_id,joined_at,consent_version",
    "topics.csv": "course_id,topic_id,topic_name",
    "messages.csv": "study_ref,course_id,conversation_id,author,kind,hint_number,"
    "request_solution,created_at",
    "exercises.csv": "study_ref,course_id,submission_id,verdict,error_type,topic_id,"
    "topic_name,created_at",
    "quiz_items.csv": "study_ref,course_id,quiz_id,position,topic_id,topic_name,"
    "difficulty,correct,answered_at",
    "tests.csv": "study_ref,course_id,phase,question_id,topic_id,topic_name,correct,"
    "submitted_at",
    "interactions.csv": "study_ref,course_id,kind,model,input_tokens,output_tokens,"
    "latency_ms,estimated_cost_usd,outcome,created_at",
}
TEST_STATEMENT = "¿Cuánto es 2(x + 1) si x = 3?"


def export(client, user, course_id: str | None = None):
    params = {"course_id": course_id} if course_id else None
    return client.get("/v1/admin/study-export", headers=user.headers, params=params)


def unpack(response) -> dict[str, list[dict]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    return {
        name: list(csv.DictReader(io.StringIO(archive.read(name).decode())))
        for name in archive.namelist()
        if name.endswith(".csv")
    }


@pytest.fixture
def study(client, db, llm, teacher, student, other_student):
    """A consenting student with every kind of activity; one who never consented."""
    room = classroom(client, teacher, student)
    topic = create_topic(client, teacher, room.course_id, "Paréntesis").json()
    conversation = open_conversation(client, student, room.course_id)
    assert ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    llm.reply = MISTAKE
    assert submit(client, student, room.course_id).status_code == 201
    quiz(db, room.course_id, student, topic, [True, False], days_ago=1)
    question = add_question(
        client, teacher, room.course_id, topic["id"], statement=TEST_STATEMENT
    ).json()
    assert set_phase(client, teacher, room.course_id, "pre", "open").status_code == 200
    taken = client.post(
        f"/v1/student/courses/{room.course_id}/test/pre",
        headers=student.headers,
        json={"answers": [{"question_id": question["id"], "choice": 0}]},
    )
    assert taken.status_code == 201, taken.text

    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    graded(db, room.course_id, other_student, 1, "incorrect", topic)
    db.commit()
    return room, topic


def test_only_the_admin_can_export(client, teacher, student, study) -> None:
    assert export(client, teacher).status_code == 403
    assert export(client, student).status_code == 403


def test_every_file_has_its_columns_and_a_readme(client, admin, study) -> None:
    response = export(client, admin)
    archive = zipfile.ZipFile(io.BytesIO(response.content))

    assert "README.md" in archive.namelist()
    for name, header in COLUMNS.items():
        assert archive.read(name).decode().splitlines()[0] == header, name


def test_the_consenting_student_activity_is_exported(client, admin, study) -> None:
    room, topic = study
    files = unpack(export(client, admin, room.course_id))

    [enrolled] = files["students.csv"]
    ref = enrolled["study_ref"]
    assert enrolled["course_id"] == room.course_id
    assert enrolled["consent_version"] == get_settings().consent_version
    assert files["topics.csv"] == [
        {
            "course_id": room.course_id,
            "topic_id": topic["id"],
            "topic_name": "Paréntesis",
        }
    ]
    assert {m["author"] for m in files["messages.csv"]} == {"student", "tutor"}
    [exercise] = files["exercises.csv"]
    assert (exercise["verdict"], exercise["error_type"]) == ("incorrect", "procedural")
    assert [i["correct"] for i in files["quiz_items.csv"]] == ["true", "false"]
    [answer] = files["tests.csv"]
    assert (answer["phase"], answer["topic_name"]) == ("pre", "Paréntesis")
    assert {i["kind"] for i in files["interactions.csv"]} >= {"chat", "exercise"}
    for name, rows in files.items():
        if name != "topics.csv":
            assert {row["study_ref"] for row in rows} == {ref}, name


def test_no_personal_data_or_free_text_leaves(
    client, admin, student, other_student, study
) -> None:
    room, _ = study
    archive = zipfile.ZipFile(io.BytesIO(export(client, admin, room.course_id).content))
    blob = b"".join(archive.read(name) for name in COLUMNS).decode()

    settings = get_settings()
    for value in (
        str(student.id),
        str(other_student.id),
        student.display_name,
        other_student.display_name,
        student_ref(settings, student.id),
        student_ref(settings, other_student.id),
        COVERED_QUESTION,
        "Según el material",
        EXERCISE["problem_statement"],
        EXERCISE["worked_answer"].splitlines()[0],
        MISTAKE["explanation"],
        MISTAKE["mistake_location"],
        "Pregunta 1",
        TEST_STATEMENT,
    ):
        assert value not in blob, value


def test_revoking_consent_removes_the_student(client, admin, student, study) -> None:
    room, _ = study
    client.delete("/v1/student/consent", headers=student.headers)

    files = unpack(export(client, admin, room.course_id))

    assert all(rows == [] for name, rows in files.items() if name != "topics.csv")


def test_a_course_filter_and_a_stable_study_ref(
    client, admin, teacher, student, study
) -> None:
    room, _ = study
    other = create_course(client, teacher)
    client.post(
        "/v1/student/enrolments",
        headers=student.headers,
        json={"class_code": other["class_code"]},
    )

    everything = unpack(export(client, admin))
    only_first = unpack(export(client, admin, room.course_id))

    # The local database may hold other courses; both of this student's are there.
    mine = {s["study_ref"] for s in only_first["students.csv"]}
    assert {
        s["course_id"] for s in everything["students.csv"] if s["study_ref"] in mine
    } == {room.course_id, other["id"]}
    assert {s["course_id"] for s in only_first["students.csv"]} == {room.course_id}
    assert (
        only_first["students.csv"][0]["study_ref"]
        == (
            unpack(export(client, admin, room.course_id))["students.csv"][0][
                "study_ref"
            ]
        )
    )
