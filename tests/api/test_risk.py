"""US2–US3 (spec 004) — at-risk students, why they are flagged, and the criteria."""

from datetime import datetime

from tests.api.activity import (
    ago,
    course_with,
    dashboard,
    exercise,
    messages,
    risk_of,
)


def at_risk(client, teacher, course_id: str) -> dict[str, list[dict]]:
    body = dashboard(client, teacher, course_id).json()
    return {s["display_name"]: s["reasons"] for s in body["at_risk"]}


def test_a_student_without_recent_activity_is_inactive(
    client, db, teacher, student, other_student
) -> None:
    course = course_with(
        client, db, teacher, student, other_student, joined_days_ago=30
    )
    messages(db, course["id"], student, 9)
    messages(db, course["id"], other_student, 2)

    flagged = at_risk(client, teacher, course["id"])

    assert list(flagged) == [student.display_name]
    [reason] = flagged[student.display_name]
    assert reason["criterion"] == "inactive"
    assert reason["days_inactive"] == 9
    assert reason["threshold_days"] == 7
    assert reason["never_active"] is False
    last = datetime.fromisoformat(reason["since"])
    assert abs((last - ago(9)).total_seconds()) < 60


def test_a_student_who_never_did_anything_counts_from_joining(
    client, db, teacher, student
) -> None:
    course = course_with(client, db, teacher, student, joined_days_ago=10)

    [reason] = at_risk(client, teacher, course["id"])[student.display_name]

    assert (reason["criterion"], reason["days_inactive"], reason["never_active"]) == (
        "inactive",
        10,
        True,
    )


def test_a_new_student_is_not_inactive_yet(client, db, teacher, student) -> None:
    course = course_with(client, db, teacher, student, joined_days_ago=3)

    assert at_risk(client, teacher, course["id"]) == {}


def test_a_high_error_rate_flags_the_student_with_the_counts(
    client, db, teacher, student
) -> None:
    course = course_with(client, db, teacher, student, joined_days_ago=30)
    for days in range(6):
        exercise(db, course["id"], student, days + 1, verdict="incorrect")
    for days in range(4):
        exercise(
            db, course["id"], student, days + 1, verdict="correct", error_type=None
        )
    exercise(db, course["id"], student, 1, verdict="not_assessed")
    exercise(db, course["id"], student, 20, verdict="incorrect")

    [reason] = at_risk(client, teacher, course["id"])[student.display_name]

    assert reason == {
        "criterion": "error_rate",
        "mistakes": 6,
        "assessed": 10,
        "window_days": 14,
        "min_exercises": 5,
        "threshold_rate": 0.6,
    }


def test_partially_correct_counts_as_a_mistake(client, db, teacher, student) -> None:
    course = course_with(client, db, teacher, student, joined_days_ago=30)
    for days in range(3):
        exercise(db, course["id"], student, days + 1, verdict="partially_correct")
    for days in range(2):
        exercise(
            db, course["id"], student, days + 1, verdict="correct", error_type=None
        )

    [reason] = at_risk(client, teacher, course["id"])[student.display_name]

    assert (reason["mistakes"], reason["assessed"]) == (3, 5)


def test_both_criteria_give_one_entry_with_two_reasons(
    client, db, teacher, student
) -> None:
    course = course_with(client, db, teacher, student, joined_days_ago=30)
    for days in range(5):
        exercise(db, course["id"], student, 8 + days, verdict="incorrect")

    reasons = at_risk(client, teacher, course["id"])[student.display_name]

    assert [r["criterion"] for r in reasons] == ["inactive", "error_rate"]


def test_few_exercises_or_only_not_assessed_do_not_flag(
    client, db, teacher, student, other_student
) -> None:
    course = course_with(
        client, db, teacher, student, other_student, joined_days_ago=30
    )
    for days in range(4):
        exercise(db, course["id"], student, days + 1, verdict="incorrect")
    for days in range(6):
        exercise(db, course["id"], other_student, days + 1, verdict="not_assessed")

    assert at_risk(client, teacher, course["id"]) == {}


def test_the_student_risk_status_has_reasons_and_weekly_activity(
    client, db, teacher, student, other_student
) -> None:
    course = course_with(
        client, db, teacher, student, other_student, joined_days_ago=60
    )
    messages(db, course["id"], student, 10, count=3)
    exercise(db, course["id"], student, 9)
    messages(db, course["id"], other_student, 1)

    flagged = risk_of(client, teacher, course["id"], student)
    fine = risk_of(client, teacher, course["id"], other_student)

    assert flagged.status_code == 200, flagged.text
    body = flagged.json()
    assert body["at_risk"] is True
    assert [r["criterion"] for r in body["reasons"]] == ["inactive"]
    assert (
        abs((datetime.fromisoformat(body["last_activity_at"]) - ago(9)).total_seconds())
        < 60
    )
    weeks = body["weekly_activity"]
    assert len(weeks) == 8
    assert weeks == sorted(weeks, key=lambda w: w["week_start"])
    assert datetime.fromisoformat(weeks[0]["week_start"]).weekday() == 0
    assert sum(w["messages"] for w in weeks) == 3
    assert sum(w["exercises"] for w in weeks) == 1
    assert body["criteria_provisional"] is True

    assert fine.json()["at_risk"] is False
    assert fine.json()["reasons"] == []


def test_the_risk_status_is_only_for_students_of_the_owned_course(
    client, db, teacher, other_teacher, student, other_student
) -> None:
    course = course_with(client, db, teacher, student)

    assert risk_of(client, other_teacher, course["id"], student).status_code == 404
    assert risk_of(client, teacher, course["id"], other_student).status_code == 404


def test_the_teacher_reads_the_criteria(client, teacher, student) -> None:
    response = client.get("/v1/teacher/risk-criteria", headers=teacher.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provisional"] is True
    assert [(c["code"], c["enabled"], c["thresholds"]) for c in body["items"]] == [
        ("inactive", True, {"days": 7}),
        ("error_rate", True, {"window_days": 14, "min_exercises": 5, "rate": 0.6}),
    ]
    assert (
        client.get("/v1/teacher/risk-criteria", headers=student.headers).status_code
        == 403
    )
