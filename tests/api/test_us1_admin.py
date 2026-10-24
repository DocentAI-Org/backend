"""US1 — the minimal admin area (FR-013)."""

from app.models import Profile


def test_admin_lists_users_with_role_and_status(
    client, admin, teacher, student
) -> None:
    response = client.get("/v1/admin/users", headers=admin.headers)

    assert response.status_code == 200
    page = response.json()
    assert {"items", "total", "limit", "offset"} <= page.keys()
    ids = {item["id"] for item in page["items"]}
    assert {str(teacher.id), str(student.id)} <= ids

    teachers = client.get("/v1/admin/users?role=teacher", headers=admin.headers).json()
    assert all(item["role"] == "teacher" for item in teachers["items"])


def test_admin_creates_teacher_account(client, db, admin, auth_admin) -> None:
    response = client.post(
        "/v1/admin/teachers",
        headers=admin.headers,
        json={"email": "elena@example.org", "display_name": "Prof. Elena"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == "teacher"
    assert body["user"]["email"] == "elena@example.org"
    assert len(body["initial_password"]) >= 12
    assert auth_admin.created == ["elena@example.org"]
    profile = db.get(Profile, body["user"]["id"])
    assert profile is not None and profile.role == "teacher"


def test_admin_creates_pseudonymous_students_in_bulk(client, db, admin) -> None:
    response = client.post(
        "/v1/admin/students/pseudonymous", headers=admin.headers, json={"count": 3}
    )

    assert response.status_code == 201
    accounts = response.json()["accounts"]
    assert len(accounts) == 3
    codes = {account["code"] for account in accounts}
    assert len(codes) == 3
    for account in accounts:
        profile = db.get(Profile, account["user_id"])
        assert profile is not None
        assert profile.role == "student"
        assert profile.email is None
        assert profile.pseudonym_code == account["code"]
        assert profile.display_name == account["code"]
        assert account["initial_password"]


def test_pseudonymous_batch_size_is_bounded(client, admin) -> None:
    for count in (0, 101):
        response = client.post(
            "/v1/admin/students/pseudonymous",
            headers=admin.headers,
            json={"count": count},
        )
        assert response.status_code == 422


def test_admin_lists_courses(client, admin, teacher) -> None:
    client.post(
        "/v1/teacher/courses", headers=teacher.headers, json={"name": "Álgebra"}
    )

    response = client.get("/v1/admin/courses", headers=admin.headers)

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert "Álgebra" in names
    course = next(
        item for item in response.json()["items"] if item["name"] == "Álgebra"
    )
    assert course["teacher_name"] == "Prof. Elena Ruiz"
    assert course["student_count"] == 0
