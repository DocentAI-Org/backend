"""US1–US2 (spec 012) — study questionnaires: the admin publishes, users see them."""

import pytest

from app.core.config import get_settings
from app.services.study_export import study_ref
from tests.api.helpers import give_consent

BASE = "/v1/admin/questionnaires"
LINK = "https://tally.so/r/abc123?ref={study_ref}"


def create(client, admin, **changes):
    body = {"title": "Satisfacción", "url": LINK, "audience": "student", **changes}
    return client.post(BASE, headers=admin.headers, json=body)


def mine(client, user) -> list[dict]:
    response = client.get("/v1/me/questionnaires", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_admin_publishes_and_manages_a_questionnaire(client, admin) -> None:
    created = create(client, admin)
    assert created.status_code == 201, created.text
    item = created.json()
    assert (item["title"], item["audience"], item["status"]) == (
        "Satisfacción",
        "student",
        "open",
    )
    assert item["url"] == LINK

    path = f"{BASE}/{item['id']}"
    closed = client.patch(
        path, headers=admin.headers, json={"status": "closed", "title": "Confianza"}
    )
    assert (closed.json()["status"], closed.json()["title"]) == ("closed", "Confianza")
    listed = client.get(BASE, headers=admin.headers).json()
    assert [q["id"] for q in listed if q["id"] == item["id"]] == [item["id"]]

    assert client.delete(path, headers=admin.headers).status_code == 204
    assert item["id"] not in {
        q["id"] for q in client.get(BASE, headers=admin.headers).json()
    }
    assert client.delete(path, headers=admin.headers).status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "http://tally.so/r/abc"},
        {"url": "javascript:alert(1)"},
        {"title": "  "},
        {"audience": "admin"},
    ],
)
def test_invalid_questionnaires_are_rejected(client, admin, changes) -> None:
    assert create(client, admin, **changes).status_code == 422


def test_only_the_admin_manages_them(client, teacher, student) -> None:
    for user in (teacher, student):
        assert client.get(BASE, headers=user.headers).status_code == 403
        assert create(client, user).status_code == 403


def test_a_consenting_student_sees_open_student_questionnaires_with_their_code(
    client, admin, student
) -> None:
    open_one = create(client, admin).json()
    closed = create(client, admin, title="Cerrado").json()
    client.patch(
        f"{BASE}/{closed['id']}", headers=admin.headers, json={"status": "closed"}
    )
    create(client, admin, title="Docentes", audience="teacher")
    give_consent(client, student)

    seen = [
        q for q in mine(client, student) if q["id"] in {open_one["id"], closed["id"]}
    ]

    ref = study_ref(get_settings(), student.id)
    assert seen == [
        {
            "id": open_one["id"],
            "title": "Satisfacción",
            "url": f"https://tally.so/r/abc123?ref={ref}",
        }
    ]
    assert all(q["title"] != "Docentes" for q in mine(client, student))


def test_without_consent_a_student_sees_none(client, admin, student) -> None:
    create(client, admin)

    assert mine(client, student) == []


def test_a_teacher_sees_teacher_questionnaires_without_any_code(
    client, admin, teacher
) -> None:
    created = create(client, admin, title="Carga docente", audience="teacher").json()

    [seen] = [q for q in mine(client, teacher) if q["id"] == created["id"]]

    assert seen["url"] == "https://tally.so/r/abc123?ref="
