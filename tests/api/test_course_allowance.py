"""US1 (spec 019) — messages per student in each course, per period, and the study's
daily ceiling across courses (5 in the tests' server values)."""

from datetime import date, timedelta

from sqlalchemy import update

from app.models import CourseUsage
from tests.api.helpers import COVERED_QUESTION, ask, classroom, open_conversation
from tests.api.test_ai_settings import set_course, set_study
from tests.api.test_us7_exercises import MISTAKE, submit

ALL_TASKS = ["tutor", "feedback", "review"]


def limit(client, teacher, course_id: str, messages, period="day", tasks=None):
    set_course(
        client,
        teacher,
        course_id,
        limits={
            "messages": messages,
            "period": period,
            "counted_tasks": ALL_TASKS if tasks is None else tasks,
        },
    )


def allowance(client, student, course_id: str) -> dict:
    response = client.get(
        f"/v1/student/courses/{course_id}/allowance", headers=student.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def send(client, student, course_id: str, times: int = 1):
    conversation = open_conversation(client, student, course_id)
    for _ in range(times):
        response = ask(client, student, course_id, conversation["id"], COVERED_QUESTION)
    return response


def test_a_weekly_limit_blocks_only_that_course(client, teacher, student) -> None:
    room = classroom(client, teacher, student)
    other = classroom(client, teacher, student)
    limit(client, teacher, room.course_id, 2, "week")

    last = send(client, student, room.course_id, times=2)
    assert last.json()["allowance"] == {
        "scope": "course",
        "limit": 2,
        "used": 2,
        "remaining": 0,
        "period": "week",
        "resets_at": last.json()["allowance"]["resets_at"],
    }
    blocked = send(client, student, room.course_id)

    assert blocked.status_code == 429
    error = blocked.json()["error"]
    assert error["code"] == "course_limit_reached"
    assert error["details"]["period"] == "week"
    resets = date.fromisoformat(error["details"]["resets_at"][:10])
    assert resets.weekday() == 0 and resets > date.today() - timedelta(days=1)
    assert send(client, student, other.course_id).status_code == 201


def test_the_limit_starts_again_with_the_next_period(
    client, db, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    limit(client, teacher, room.course_id, 1, "week")
    send(client, student, room.course_id)
    db.execute(
        update(CourseUsage).values(
            period_start=CourseUsage.period_start - timedelta(days=7)
        )
    )
    db.commit()

    assert send(client, student, room.course_id).status_code == 201


def test_a_limit_for_the_whole_course_never_resets(client, teacher, student) -> None:
    room = classroom(client, teacher, student)
    limit(client, teacher, room.course_id, 1, "course")
    send(client, student, room.course_id)

    body = allowance(client, student, room.course_id)
    assert body["period"] == "course" and body["resets_at"] is None
    blocked = send(client, student, room.course_id)
    assert blocked.json()["error"]["details"]["resets_at"] is None


def test_without_a_course_limit_the_daily_ceiling_still_applies(
    client, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    send(client, student, room.course_id, times=2)

    body = allowance(client, student, room.course_id)
    assert body["scope"] == "daily"
    assert (body["limit"], body["used"], body["remaining"]) == (5, 2, 3)
    assert body["period"] == "day" and body["resets_at"] is not None


def test_the_tighter_of_course_and_ceiling_is_shown(client, teacher, student) -> None:
    room = classroom(client, teacher, student)
    other = classroom(client, teacher, student)
    limit(client, teacher, room.course_id, 3, "week")
    send(client, student, other.course_id, times=4)

    body = allowance(client, student, room.course_id)
    assert (body["scope"], body["remaining"]) == ("daily", 1)
    send(client, student, room.course_id)
    blocked = send(client, student, room.course_id)
    assert blocked.json()["error"]["code"] == "daily_limit_reached"


def test_with_no_ceiling_and_no_limit_nothing_blocks(
    client, admin, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    set_study(client, admin, ceiling={"messages": None})

    assert send(client, student, room.course_id, times=6).status_code == 201
    body = allowance(client, student, room.course_id)
    assert body == {
        "scope": "course",
        "limit": None,
        "used": 6,
        "remaining": None,
        "period": "day",
        "resets_at": body["resets_at"],
    }


def test_tasks_the_teacher_does_not_count_use_no_messages(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    limit(client, teacher, room.course_id, 1, "day", tasks=["tutor"])
    llm.reply = MISTAKE

    assert submit(client, student, room.course_id).status_code == 201
    assert submit(client, student, room.course_id).status_code == 201
    assert allowance(client, student, room.course_id)["used"] == 0
    # The daily ceiling counts every message (cost safety net).
    daily = client.get("/v1/student/allowance", headers=student.headers).json()
    assert daily["used"] == 2


def test_a_failed_reply_gives_the_message_back(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    limit(client, teacher, room.course_id, 1, "week")
    llm.fail_chat = True

    assert send(client, student, room.course_id).status_code == 503
    assert allowance(client, student, room.course_id)["used"] == 0
    llm.fail_chat = False
    assert send(client, student, room.course_id).status_code == 201


def test_only_enrolled_students_read_a_course_allowance(
    client, teacher, student, other_student
) -> None:
    room = classroom(client, teacher, student)

    response = client.get(
        f"/v1/student/courses/{room.course_id}/allowance",
        headers=other_student.headers,
    )
    assert response.status_code in (403, 404)
