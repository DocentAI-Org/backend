"""US2 — student side of joining courses (T1)."""

from tests.api.test_us2_courses import create_course


def join(client, student, code: str):
    return client.post(
        "/v1/student/enrolments", headers=student.headers, json={"class_code": code}
    )


def test_student_joins_with_code_and_sees_course(client, teacher, student) -> None:
    course = create_course(client, teacher)

    response = join(client, student, course["class_code"])

    assert response.status_code == 200
    joined = response.json()
    assert joined["id"] == course["id"]
    assert joined["name"] == "Álgebra"
    assert joined["teacher_name"] == "Prof. Elena Ruiz"
    assert joined["disclosure_acknowledged"] is False
    assert "class_code" not in joined

    listed = client.get("/v1/student/courses", headers=student.headers).json()
    assert [c["id"] for c in listed["items"]] == [course["id"]]


def test_code_is_case_insensitive_and_join_is_idempotent(
    client, teacher, student
) -> None:
    course = create_course(client, teacher)

    first = join(client, student, course["class_code"].lower())
    second = join(client, student, course["class_code"])

    assert first.status_code == second.status_code == 200
    students = client.get(
        f"/v1/teacher/courses/{course['id']}/students", headers=teacher.headers
    ).json()
    assert students["total"] == 1


def test_unknown_code_is_invalid(client, student) -> None:
    response = join(client, student, "ZZZ-9999")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "class_code_invalid"


def test_revoked_student_cannot_rejoin(client, teacher, student) -> None:
    course = create_course(client, teacher)
    join(client, student, course["class_code"])
    client.delete(
        f"/v1/teacher/courses/{course['id']}/students/{student.id}",
        headers=teacher.headers,
    )

    response = join(client, student, course["class_code"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "enrolment_revoked"


def test_student_cannot_see_courses_they_are_not_in(
    client, teacher, student, other_student
) -> None:
    course = create_course(client, teacher)
    join(client, other_student, course["class_code"])

    response = client.get(
        f"/v1/student/courses/{course['id']}", headers=student.headers
    )

    assert response.status_code == 404
    listed = client.get("/v1/student/courses", headers=student.headers).json()
    assert listed["items"] == []
