"""US2 — teacher side of courses and class codes (T1)."""

import re


def create_course(client, teacher, name: str = "Álgebra") -> dict:
    response = client.post(
        "/v1/teacher/courses",
        headers=teacher.headers,
        json={"name": name, "description": "Ecuaciones de primer grado"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_teacher_creates_course_with_active_code(client, teacher) -> None:
    course = create_course(client, teacher)

    assert course["name"] == "Álgebra"
    assert course["description"] == "Ecuaciones de primer grado"
    assert re.fullmatch(r"[A-Z0-9]{3}-[A-Z0-9]{4}", course["class_code"])
    assert course["class_code_active"] is True
    assert course["invitation_path"] == f"/unirse/{course['class_code']}"
    assert course["student_count"] == 0


def test_course_name_is_validated(client, teacher) -> None:
    for name in ("", "x" * 81):
        response = client.post(
            "/v1/teacher/courses", headers=teacher.headers, json={"name": name}
        )
        assert response.status_code == 422


def test_teacher_sees_only_own_courses(client, teacher, other_teacher) -> None:
    mine = create_course(client, teacher, "Mío")
    theirs = create_course(client, other_teacher, "Suyo")

    listed = client.get("/v1/teacher/courses", headers=teacher.headers).json()
    assert [c["id"] for c in listed["items"]] == [mine["id"]]

    response = client.get(
        f"/v1/teacher/courses/{theirs['id']}", headers=teacher.headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    patch = client.patch(
        f"/v1/teacher/courses/{theirs['id']}",
        headers=teacher.headers,
        json={"name": "Robado"},
    )
    assert patch.status_code == 404


def test_teacher_updates_course(client, teacher) -> None:
    course = create_course(client, teacher)

    response = client.patch(
        f"/v1/teacher/courses/{course['id']}",
        headers=teacher.headers,
        json={"name": "Álgebra II"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Álgebra II"
    assert response.json()["description"] == "Ecuaciones de primer grado"


def test_regenerate_and_disable_class_code(client, teacher, student) -> None:
    course = create_course(client, teacher)
    old_code = course["class_code"]

    regenerated = client.post(
        f"/v1/teacher/courses/{course['id']}/class-code/regenerate",
        headers=teacher.headers,
    ).json()
    assert regenerated["class_code"] != old_code

    old = client.post(
        "/v1/student/enrolments", headers=student.headers, json={"class_code": old_code}
    )
    assert old.status_code == 400
    assert old.json()["error"]["code"] == "class_code_invalid"

    disabled = client.patch(
        f"/v1/teacher/courses/{course['id']}/class-code",
        headers=teacher.headers,
        json={"active": False},
    ).json()
    assert disabled["class_code_active"] is False

    response = client.post(
        "/v1/student/enrolments",
        headers=student.headers,
        json={"class_code": regenerated["class_code"]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "class_code_disabled"


def test_teacher_lists_students_and_revokes(client, teacher, student) -> None:
    course = create_course(client, teacher)
    client.post(
        "/v1/student/enrolments",
        headers=student.headers,
        json={"class_code": course["class_code"]},
    )

    students = client.get(
        f"/v1/teacher/courses/{course['id']}/students", headers=teacher.headers
    ).json()
    assert students["total"] == 1
    entry = students["items"][0]
    assert entry == {
        "student_id": str(student.id),
        "display_name": "Lucas Herrera",
        "joined_at": entry["joined_at"],
        "status": "active",
    }
    assert "email" not in entry

    revoke = client.delete(
        f"/v1/teacher/courses/{course['id']}/students/{student.id}",
        headers=teacher.headers,
    )
    assert revoke.status_code == 204

    detail = client.get(f"/v1/student/courses/{course['id']}", headers=student.headers)
    assert detail.status_code == 403
    assert detail.json()["error"]["code"] == "enrolment_revoked"
