"""US1 — authentication and role-limited access (P1)."""

from sqlalchemy import text

from app.models import Profile
from tests.conftest import make_token
from tests.fakes import insert_auth_user


def test_request_without_token_is_unauthenticated(client) -> None:
    response = client.get("/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_expired_or_forged_token_is_unauthenticated(client, student) -> None:
    expired = make_token(student.id, expires_in=-10)
    forged = student.token[:-4] + "abcd"

    for token in (expired, forged, "not-a-jwt"):
        response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"


def test_student_reads_only_their_own_profile(client, student, other_student) -> None:
    response = client.get("/v1/me", headers=student.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(student.id)
    assert body["role"] == "student"
    assert body["display_name"] == "Lucas Herrera"
    assert body["preferred_language"] == "es"
    assert body["is_pseudonymous"] is False
    assert str(other_student.id) not in response.text


def test_user_updates_preferred_language(client, teacher) -> None:
    response = client.patch(
        "/v1/me", headers=teacher.headers, json={"preferred_language": "en"}
    )

    assert response.status_code == 200
    assert response.json()["preferred_language"] == "en"

    invalid = client.patch(
        "/v1/me", headers=teacher.headers, json={"preferred_language": "fr"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_disabled_account_is_forbidden(client, db, student) -> None:
    db.get(Profile, student.id).status = "disabled"
    db.commit()

    response = client.get("/v1/me", headers=student.headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_self_registration_always_creates_a_student(db) -> None:
    user_id = insert_auth_user(db, "nueva@example.org", "Nueva Alumna")
    # A malicious sign-up cannot choose its own role through metadata.
    db.execute(
        text(
            "update auth.users set raw_user_meta_data = raw_user_meta_data || "
            '\'{"role": "admin"}\' where id = :id'
        ),
        {"id": user_id},
    )
    db.flush()

    profile = db.get(Profile, user_id)
    assert profile is not None
    assert profile.role == "student"
    assert profile.display_name == "Nueva Alumna"
    assert profile.email == "nueva@example.org"


def test_role_routers_reject_other_roles(client, admin, teacher, student) -> None:
    cases = [
        ("/v1/admin/users", teacher),
        ("/v1/admin/users", student),
        ("/v1/teacher/courses", student),
        ("/v1/teacher/courses", admin),
        ("/v1/student/courses", teacher),
        ("/v1/student/courses", admin),
    ]
    for path, user in cases:
        response = client.get(path, headers=user.headers)
        assert response.status_code == 403, (path, user.role)
        assert response.json()["error"]["code"] == "forbidden"
