"""002 US2 and US3 — course corrections list and corrected marker."""

from tests.api.helpers import (
    COVERED_QUESTION,
    ask,
    classroom,
    open_conversation,
)
from tests.api.test_us7_exercises import submit

FLAG = {"category": "incorrect", "correction": "Hay que dividir entre 2."}


def _flagged_course(client, teacher, student):
    room = classroom(client, teacher, student)
    flagged = open_conversation(client, student, room.course_id)
    exchange = ask(
        client, student, room.course_id, flagged["id"], COVERED_QUESTION
    ).json()
    plain = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, plain["id"], COVERED_QUESTION)
    submission = submit(client, student, room.course_id).json()
    base = f"/v1/teacher/courses/{room.course_id}"
    client.put(
        f"{base}/messages/{exchange['tutor_message']['id']}/flag",
        headers=teacher.headers,
        json=FLAG,
    )
    client.put(
        f"{base}/submissions/{submission['id']}/flag",
        headers=teacher.headers,
        json={"category": "poor", "correction": "Revisa el signo."},
    )
    return room, flagged, plain, exchange, submission


def test_teacher_lists_course_flags_with_their_targets(
    client, teacher, student
) -> None:
    room, flagged, _, exchange, submission = _flagged_course(client, teacher, student)

    page = client.get(
        f"/v1/teacher/courses/{room.course_id}/flags", headers=teacher.headers
    ).json()

    assert page["total"] == 2
    by_target = {item["target"]: item for item in page["items"]}
    message_flag = by_target["message"]
    assert message_flag["category"] == "incorrect"
    assert message_flag["correction"] == FLAG["correction"]
    assert message_flag["author_name"] == "Prof. Elena Ruiz"
    assert message_flag["student_name"] == "Lucas Herrera"
    assert message_flag["original_text"] == exchange["tutor_message"]["text"]
    assert message_flag["conversation_id"] == flagged["id"]
    assert message_flag["message_id"] == exchange["tutor_message"]["id"]
    assert message_flag["submission_id"] is None

    submission_flag = by_target["submission"]
    assert submission_flag["submission_id"] == submission["id"]
    assert submission_flag["original_text"] == submission["explanation"]
    assert submission_flag["conversation_id"] is None
    # Newest first.
    assert page["items"][0]["target"] == "submission"


def test_other_teacher_cannot_list_flags(
    client, teacher, other_teacher, student
) -> None:
    room, *_ = _flagged_course(client, teacher, student)

    response = client.get(
        f"/v1/teacher/courses/{room.course_id}/flags", headers=other_teacher.headers
    )

    assert response.status_code == 404


def test_conversation_summaries_mark_and_filter_corrections(
    client, teacher, student
) -> None:
    room, flagged, plain, *_ = _flagged_course(client, teacher, student)
    base = f"/v1/teacher/courses/{room.course_id}/conversations"

    listed = client.get(base, headers=teacher.headers).json()["items"]
    marks = {c["id"]: c["has_correction"] for c in listed}
    assert marks == {flagged["id"]: True, plain["id"]: False}

    corrected = client.get(
        f"{base}?has_correction=true", headers=teacher.headers
    ).json()["items"]
    assert [c["id"] for c in corrected] == [flagged["id"]]
    uncorrected = client.get(
        f"{base}?has_correction=false", headers=teacher.headers
    ).json()["items"]
    assert [c["id"] for c in uncorrected] == [plain["id"]]

    detail = client.get(f"{base}/{flagged['id']}", headers=teacher.headers).json()
    assert detail["has_correction"] is True
