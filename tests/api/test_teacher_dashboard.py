"""US1 (spec 004) — the teacher sees recurring errors by topic and by student."""

from tests.api.activity import course_with, dashboard, exercise, messages
from tests.api.test_us6_topics import create_topic


def topic(client, teacher, course_id: str, name: str) -> dict:
    response = create_topic(client, teacher, course_id, name)
    assert response.status_code == 201, response.text
    return response.json()


def test_errors_are_grouped_by_topic_and_by_student_within_the_period(
    client, db, teacher, student, other_student
) -> None:
    course = course_with(client, db, teacher, student, other_student)
    cid = course["id"]
    brackets = topic(client, teacher, cid, "Paréntesis")
    isolate = topic(client, teacher, cid, "Despejar la incógnita")
    for _ in range(3):
        exercise(db, cid, student, 2, error_type="procedural", topic=brackets)
    exercise(db, cid, student, 3, error_type="execution", topic=isolate)
    exercise(db, cid, other_student, 4, error_type="conceptual", topic=brackets)
    exercise(db, cid, other_student, 20, error_type="conceptual", topic=isolate)
    exercise(db, cid, student, 1, verdict="correct", error_type=None)

    week = dashboard(client, teacher, cid, "7d")

    assert week.status_code == 200, week.text
    body = week.json()
    assert body["period"] == "7d"
    assert [
        (t["topic_name"], t["errors"], t["students"], t["top_error_type"])
        for t in body["errors_by_topic"]
    ] == [
        ("Paréntesis", 4, 2, "procedural"),
        ("Despejar la incógnita", 1, 1, "execution"),
    ]
    assert body["errors_by_topic"][0]["topic_id"] == brackets["id"]
    assert [
        (s["display_name"], s["errors"], s["top_error_type"], s["top_topic_name"])
        for s in body["errors_by_student"]
    ] == [
        (student.display_name, 4, "procedural", "Paréntesis"),
        (other_student.display_name, 1, "conceptual", "Paréntesis"),
    ]
    assert body["activity"] == {"messages": 0, "exercises": 6}
    assert body["criteria_provisional"] is True

    month = dashboard(client, teacher, cid).json()
    assert month["period"] == "30d"
    assert sum(t["errors"] for t in month["errors_by_topic"]) == 6

    whole = dashboard(client, teacher, cid, "all").json()
    assert whole["period"] == "all"
    assert whole["since"] is None


def test_ties_are_broken_by_taxonomy_order(client, db, teacher, student) -> None:
    course = course_with(client, db, teacher, student)
    exercise(db, course["id"], student, 1, error_type="execution")
    exercise(db, course["id"], student, 1, error_type="conceptual")

    body = dashboard(client, teacher, course["id"]).json()

    assert body["errors_by_student"][0]["top_error_type"] == "conceptual"


def test_entries_without_topic_or_of_a_deleted_topic(
    client, db, teacher, student
) -> None:
    course = course_with(client, db, teacher, student)
    cid = course["id"]
    exercise(db, cid, student, 1, error_type="procedural")
    exercise(db, cid, student, 1, error_type="procedural", topic_name="Fracciones")

    groups = {
        (t["topic_id"], t["topic_name"], t["topic_deleted"]): t["errors"]
        for t in dashboard(client, teacher, cid).json()["errors_by_topic"]
    }

    assert groups == {(None, None, False): 1, (None, "Fracciones", True): 1}


def test_the_v1_placeholder_type_is_not_counted(client, db, teacher, student) -> None:
    course = course_with(client, db, teacher, student)
    exercise(db, course["id"], student, 1, error_type="placeholder", is_stub=True)

    body = dashboard(client, teacher, course["id"]).json()

    assert body["errors_by_topic"] == []
    assert body["errors_by_student"] == []


def test_too_little_activity_says_what_is_missing(client, db, teacher, student) -> None:
    course = course_with(client, db, teacher, student)
    messages(db, course["id"], student, 1, count=12)
    exercise(db, course["id"], student, 1)
    exercise(db, course["id"], student, 2, verdict="not_assessed")

    body = dashboard(client, teacher, course["id"]).json()

    assert body["enough_data"] is False
    assert body["activity"] == {"messages": 12, "exercises": 2}
    assert body["thresholds"] == {"messages": 20, "exercises": 5}

    for days in range(3):
        exercise(db, course["id"], student, days, verdict="correct", error_type=None)
    assert dashboard(client, teacher, course["id"]).json()["enough_data"] is True


def test_revoked_students_are_left_out(
    client, db, teacher, student, other_student
) -> None:
    course = course_with(client, db, teacher, student, other_student)
    exercise(db, course["id"], student, 1)
    exercise(db, course["id"], other_student, 1)
    client.delete(
        f"/v1/teacher/courses/{course['id']}/students/{other_student.id}",
        headers=teacher.headers,
    )

    body = dashboard(client, teacher, course["id"]).json()

    assert [s["display_name"] for s in body["errors_by_student"]] == [
        student.display_name
    ]
    assert body["errors_by_topic"][0]["errors"] == 1
    assert body["activity"]["exercises"] == 1


def test_only_the_owner_reads_the_dashboard(
    client, db, teacher, other_teacher, student
) -> None:
    course = course_with(client, db, teacher, student)

    assert dashboard(client, other_teacher, course["id"]).status_code == 404
    assert dashboard(client, student, course["id"]).status_code == 403
    assert dashboard(client, teacher, course["id"], "90d").status_code == 422
