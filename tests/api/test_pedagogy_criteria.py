"""US1–US3 (spec 015) — study defaults, course overrides, every feature follows them."""

import pytest

from tests.api.activity import course_with, dashboard, messages
from tests.api.helpers import classroom
from tests.api.test_adaptation import chat, mistakes
from tests.api.test_progress import graded, progress, quiz
from tests.api.test_repeated_mistakes import mistakes as submit_mistakes
from tests.api.test_us2_courses import create_course
from tests.api.test_us6_topics import create_topic

ADMIN = "/v1/admin/pedagogy-criteria"
DEFAULTS = {
    "inactive": {"enabled": True, "days": 7},
    "error_rate": {"enabled": True, "rate": 0.6, "min_exercises": 5, "window_days": 14},
    "repeated_mistakes": {"count": 3, "window_days": 30},
    "adaptation": {"enabled": True},
    "mastery": {"window": 10, "min_items": 3, "progressing": 0.5, "mastered": 0.8},
    "quiz": {"length": 5, "streak": 2, "start_level": 2, "adaptive": True},
}
NO_OVERRIDES = dict.fromkeys(DEFAULTS)


def course_path(course_id: str) -> str:
    return f"/v1/teacher/courses/{course_id}/pedagogy-criteria"


def set_course(client, teacher, course_id: str, **groups):
    response = client.put(
        course_path(course_id),
        headers=teacher.headers,
        json={**NO_OVERRIDES, **groups},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_study_defaults_are_todays_values(client, admin) -> None:
    body = client.get(ADMIN, headers=admin.headers).json()

    assert body["criteria"] == DEFAULTS
    assert body["provisional"] is True


def test_the_admin_changes_the_defaults_for_every_course(
    client, admin, teacher
) -> None:
    course = create_course(client, teacher)
    changed = {**DEFAULTS, "inactive": {"enabled": True, "days": 5}}

    response = client.put(
        ADMIN, headers=admin.headers, json={"criteria": changed, "provisional": False}
    )

    assert response.status_code == 200, response.text
    assert response.json()["provisional"] is False
    seen = client.get(course_path(course["id"]), headers=teacher.headers).json()
    assert seen["effective"]["inactive"] == {"enabled": True, "days": 5}
    assert seen["study"] == changed and seen["provisional"] is False


@pytest.mark.parametrize(
    "group",
    [
        {"error_rate": {**DEFAULTS["error_rate"], "rate": 1.5}},
        {"mastery": {**DEFAULTS["mastery"], "progressing": 0.9}},
        {"mastery": {**DEFAULTS["mastery"], "min_items": 11}},
        {"inactive": {"enabled": True, "days": 0}},
        {"repeated_mistakes": {"count": 0, "window_days": 30}},
    ],
)
def test_invalid_criteria_are_rejected(client, admin, teacher, group) -> None:
    course = create_course(client, teacher)
    body = {"criteria": {**DEFAULTS, **group}, "provisional": True}

    assert client.put(ADMIN, headers=admin.headers, json=body).status_code == 422
    assert (
        client.put(
            course_path(course["id"]),
            headers=teacher.headers,
            json={**NO_OVERRIDES, **group},
        ).status_code
        == 422
    )
    assert client.get(ADMIN, headers=admin.headers).json()["criteria"] == DEFAULTS


def test_only_the_admin_sets_defaults_and_only_the_owner_a_course(
    client, teacher, other_teacher, student
) -> None:
    course = create_course(client, teacher)
    for user in (teacher, student):
        assert client.get(ADMIN, headers=user.headers).status_code == 403
    assert (
        client.get(course_path(course["id"]), headers=other_teacher.headers).status_code
        == 404
    )


def test_a_course_overrides_a_group_and_can_go_back(client, teacher) -> None:
    course = create_course(client, teacher)

    body = set_course(
        client, teacher, course["id"], mastery={**DEFAULTS["mastery"], "mastered": 0.7}
    )

    assert body["custom"] == {**dict.fromkeys(DEFAULTS, False), "mastery": True}
    assert body["effective"]["mastery"]["mastered"] == 0.7
    assert body["effective"]["inactive"] == DEFAULTS["inactive"]
    back = set_course(client, teacher, course["id"])
    assert back["effective"] == DEFAULTS
    assert not any(back["custom"].values())


def test_the_dashboard_uses_the_course_inactivity(client, db, teacher, student) -> None:
    strict = course_with(client, db, teacher, student, joined_days_ago=30)
    usual = course_with(client, db, teacher, student, joined_days_ago=30)
    for course in (strict, usual):
        messages(db, course["id"], student, 4)
    set_course(client, teacher, strict["id"], inactive={"enabled": True, "days": 3})

    flagged = dashboard(client, teacher, strict["id"]).json()["at_risk"]
    calm = dashboard(client, teacher, usual["id"]).json()["at_risk"]

    assert [s["display_name"] for s in flagged] == [student.display_name]
    assert flagged[0]["reasons"][0]["threshold_days"] == 3
    assert calm == []


def test_the_repeated_mistake_threshold_is_the_courses(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    set_course(
        client,
        teacher,
        room.course_id,
        repeated_mistakes={"count": 2, "window_days": 30},
    )
    create_topic(client, teacher, room.course_id, "Paréntesis")

    made = submit_mistakes(client, llm, student, room.course_id, 2)

    assert made[0]["repeated_mistake"] is None
    assert made[1]["repeated_mistake"]["count"] == 2


def test_adaptation_can_be_turned_off_in_a_course(
    client, db, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    set_course(client, teacher, room.course_id, adaptation={"enabled": False})
    mistakes(db, room.course_id, student, 1, 3, "procedural")

    assert chat(client, student, room.course_id)["tutor_message"]["adaptation"] is None


def test_progress_follows_the_course_mastery(client, db, teacher, student) -> None:
    course = course_with(client, db, teacher, student, joined_days_ago=60)
    parens = create_topic(client, teacher, course["id"], "Paréntesis").json()
    for days, verdict in ((5, "correct"), (4, "partially_correct"), (3, "incorrect")):
        graded(db, course["id"], student, days, verdict, parens)
    quiz(db, course["id"], student, parens, [True, False, True], days_ago=1)
    mastery = {**DEFAULTS["mastery"], "mastered": 0.55}
    set_course(client, teacher, course["id"], mastery=mastery)

    body = progress(client, student, course["id"]).json()

    assert body["criteria"] == mastery
    [topic] = [t for t in body["topics"] if t["topic_name"] == "Paréntesis"]
    assert topic["level"] == "mastered"
