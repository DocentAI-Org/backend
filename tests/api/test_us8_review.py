"""US8 — teacher reviews conversations and corrects poor answers (T4, T6)."""

from tests.api.helpers import (
    COVERED_QUESTION,
    UNCOVERED_QUESTION,
    ask,
    classroom,
    open_conversation,
)
from tests.api.test_us7_exercises import submit


def _conversation_with_answer(client, teacher, student):
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    exchange = ask(
        client, student, room.course_id, conversation["id"], COVERED_QUESTION
    ).json()
    return room, conversation, exchange


def test_teacher_lists_and_filters_conversations(
    client, teacher, student, other_student
) -> None:
    room, conversation, _ = _conversation_with_answer(client, teacher, student)
    client.post(
        "/v1/student/enrolments",
        headers=other_student.headers,
        json={"class_code": room.course["class_code"]},
    )
    client.post(
        f"/v1/student/courses/{room.course_id}/disclosure",
        headers=other_student.headers,
    )
    other = open_conversation(client, other_student, room.course_id)
    ask(client, other_student, room.course_id, other["id"], UNCOVERED_QUESTION)
    base = f"/v1/teacher/courses/{room.course_id}/conversations"

    listed = client.get(base, headers=teacher.headers).json()
    assert listed["total"] == 2
    summary = next(c for c in listed["items"] if c["id"] == conversation["id"])
    assert summary["student_name"] == "Lucas Herrera"
    assert summary["message_count"] == 2
    assert summary["has_no_source"] is False
    assert "email" not in summary

    no_source = client.get(f"{base}?has_no_source=true", headers=teacher.headers).json()
    assert [c["id"] for c in no_source["items"]] == [other["id"]]

    by_student = client.get(
        f"{base}?student_id={student.id}", headers=teacher.headers
    ).json()
    assert [c["id"] for c in by_student["items"]] == [conversation["id"]]

    future = client.get(
        f"{base}?from=2999-01-01T00:00:00Z", headers=teacher.headers
    ).json()
    assert future["total"] == 0

    detail = client.get(f"{base}/{conversation['id']}", headers=teacher.headers).json()
    assert [m["author"] for m in detail["messages"]] == ["student", "tutor"]
    assert detail["messages"][1]["flag"] is None


def test_flag_and_correction_reach_the_student_without_category(
    client, teacher, student
) -> None:
    room, conversation, exchange = _conversation_with_answer(client, teacher, student)
    tutor_id = exchange["tutor_message"]["id"]
    flag_path = f"/v1/teacher/courses/{room.course_id}/messages/{tutor_id}/flag"

    flagged = client.put(
        flag_path,
        headers=teacher.headers,
        json={"category": "incorrect", "correction": "Hay que dividir entre 2."},
    )
    assert flagged.status_code == 200
    flag = flagged.json()
    assert flag["category"] == "incorrect"
    assert flag["author_name"] == "Prof. Elena Ruiz"

    student_view = client.get(
        f"/v1/student/courses/{room.course_id}/conversations/{conversation['id']}",
        headers=student.headers,
    ).json()
    corrected = student_view["messages"][1]
    assert corrected["correction"]["text"] == "Hay que dividir entre 2."
    assert corrected["correction"]["reviewed_at"]
    assert "category" not in corrected["correction"]
    assert "incorrect" not in str(corrected)

    edited = client.put(
        flag_path,
        headers=teacher.headers,
        json={"category": "poor", "correction": "Mejor: divide entre 2."},
    )
    assert edited.json()["id"] == flag["id"]
    teacher_view = client.get(
        f"/v1/teacher/courses/{room.course_id}/conversations/{conversation['id']}",
        headers=teacher.headers,
    ).json()
    assert teacher_view["messages"][1]["flag"]["category"] == "poor"

    removed = client.delete(flag_path, headers=teacher.headers)
    assert removed.status_code == 204
    student_view = client.get(
        f"/v1/student/courses/{room.course_id}/conversations/{conversation['id']}",
        headers=student.headers,
    ).json()
    assert student_view["messages"][1]["correction"] is None


def test_only_tutor_messages_can_be_flagged(client, teacher, student) -> None:
    room, _, exchange = _conversation_with_answer(client, teacher, student)
    student_message_id = exchange["student_message"]["id"]

    response = client.put(
        f"/v1/teacher/courses/{room.course_id}/messages/{student_message_id}/flag",
        headers=teacher.headers,
        json={"category": "poor", "correction": "x"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "not_a_tutor_message"


def test_teacher_reviews_and_flags_submissions(client, teacher, student) -> None:
    room = classroom(client, teacher, student)
    submission = submit(client, student, room.course_id).json()
    base = f"/v1/teacher/courses/{room.course_id}/submissions"

    listed = client.get(base, headers=teacher.headers).json()
    assert listed["items"][0]["student_name"] == "Lucas Herrera"
    assert listed["items"][0]["flag"] is None

    client.put(
        f"{base}/{submission['id']}/flag",
        headers=teacher.headers,
        json={"category": "incorrect", "correction": "El error es de signo."},
    )

    detail = client.get(f"{base}/{submission['id']}", headers=teacher.headers).json()
    assert detail["flag"]["correction"] == "El error es de signo."
    student_view = client.get(
        f"/v1/student/courses/{room.course_id}/submissions/{submission['id']}",
        headers=student.headers,
    ).json()
    assert student_view["correction"]["text"] == "El error es de signo."


def test_other_teacher_cannot_review_or_flag(
    client, teacher, other_teacher, student
) -> None:
    room, conversation, exchange = _conversation_with_answer(client, teacher, student)
    base = f"/v1/teacher/courses/{room.course_id}"

    for method, path, body in [
        ("get", f"{base}/conversations", None),
        ("get", f"{base}/conversations/{conversation['id']}", None),
        ("get", f"{base}/submissions", None),
        (
            "put",
            f"{base}/messages/{exchange['tutor_message']['id']}/flag",
            {"category": "poor", "correction": "x"},
        ),
    ]:
        response = client.request(
            method, path, headers=other_teacher.headers, json=body
        )
        assert response.status_code == 404, path


def test_admin_exports_the_evaluation_set(client, admin, teacher, student) -> None:
    room, _, exchange = _conversation_with_answer(client, teacher, student)
    client.put(
        f"/v1/teacher/courses/{room.course_id}/messages/"
        f"{exchange['tutor_message']['id']}/flag",
        headers=teacher.headers,
        json={"category": "incorrect", "correction": "Hay que dividir entre 2."},
    )

    items = client.get("/v1/admin/evaluation-set", headers=admin.headers).json()[
        "items"
    ]

    item = next(i for i in items if i["course_id"] == room.course_id)
    assert item["question"] == COVERED_QUESTION
    assert item["original_answer"] == exchange["tutor_message"]["text"]
    assert item["correction"] == "Hay que dividir entre 2."
    assert item["citations"][0]["document_name"] == "ecuaciones.md"
    assert "Lucas" not in str(item)
