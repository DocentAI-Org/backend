"""US3 (spec 019) — credentials for commercial models: the study's, offered to every
course, and a teacher's own when the admin allows it. Keys are encrypted and never shown
again."""

import logging

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.models import LLMCredential
from tests.api.helpers import classroom
from tests.api.test_ai_settings import NO_MODELS, course_path, set_course, set_study
from tests.api.test_study_export import export
from tests.api.test_us2_courses import create_course
from tests.api.test_us7_exercises import MISTAKE, submit

ADMIN = "/v1/admin/llm-credentials"
KEY = "sk-test-0123456789abcdef"
OPENAI = {"provider": "openai", "label": "OpenAI UNI", "api_key": KEY}


def own_path(course_id: str) -> str:
    return f"/v1/teacher/courses/{course_id}/llm-credentials"


def add_study(client, admin, body: dict | None = None) -> dict:
    response = client.post(ADMIN, headers=admin.headers, json=body or OPENAI)
    assert response.status_code == 201, response.text
    return response.json()


def gpt(credential: dict, model: str = "gpt-test") -> dict:
    return {"provider": "openai", "model": model, "credential_id": credential["id"]}


def sources(client, teacher, course_id: str) -> dict:
    body = client.get(
        f"/v1/teacher/courses/{course_id}/ai-models", headers=teacher.headers
    ).json()
    return {s["credential_id"] or s["provider"]: s for s in body["sources"]}


def allow_teacher_keys(client, admin, allowed: bool = True) -> None:
    set_study(client, admin, allow_teacher_keys=allowed)


def test_the_admin_adds_a_key_that_is_stored_encrypted(client, db, admin) -> None:
    body = add_study(client, admin)

    assert body["label"] == "OpenAI UNI" and body["provider"] == "openai"
    assert body["key_hint"] == "…cdef" and body["scope"] == "study"
    assert KEY not in str(body)
    stored = db.scalar(select(LLMCredential.encrypted_key))
    assert stored and KEY not in stored
    listed = client.get(ADMIN, headers=admin.headers).json()
    assert [c["id"] for c in listed["items"]] == [body["id"]]
    assert {s["provider"] for s in listed["server"]} == {"ollama", "anthropic"}


@pytest.mark.parametrize(
    ("key", "code"),
    [("bad-key-123456", "key_rejected"), ("down-key-123456", "provider_unreachable")],
)
def test_a_key_the_provider_does_not_accept_is_not_stored(
    client, db, admin, key, code
) -> None:
    response = client.post(
        ADMIN, headers=admin.headers, json={**OPENAI, "api_key": key}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert key not in response.text
    assert db.scalar(select(LLMCredential.id)) is None


def test_an_openai_compatible_key_needs_its_address(client, admin) -> None:
    body = {**OPENAI, "provider": "openai_compatible"}

    assert client.post(ADMIN, headers=admin.headers, json=body).status_code == 422
    with_url = {**body, "base_url": "https://api.mistral.ai/v1"}
    assert add_study(client, admin, with_url)["base_url"] == "https://api.mistral.ai/v1"


def test_without_a_master_key_no_key_can_be_stored(client, admin, monkeypatch) -> None:
    monkeypatch.delenv("LLM_CREDENTIALS_KEY")
    get_settings.cache_clear()
    try:
        response = client.post(ADMIN, headers=admin.headers, json=OPENAI)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "credentials_not_configured"


def test_courses_use_the_models_the_admin_offers(client, llm, admin, teacher, student):
    credential = add_study(client, admin)
    offered = client.patch(
        f"{ADMIN}/{credential['id']}",
        headers=admin.headers,
        json={"offered_models": ["gpt-test"]},
    )
    assert offered.status_code == 200, offered.text
    room = classroom(client, teacher, student)

    seen = sources(client, teacher, room.course_id)[credential["id"]]
    assert seen["label"] == "OpenAI UNI" and seen["scope"] == "study"
    assert [m["id"] for m in seen["models"]] == ["gpt-test"]
    refused = client.put(
        course_path(room.course_id),
        headers=teacher.headers,
        json={"models": {**NO_MODELS, "feedback": gpt(credential, "gpt-mini")}},
    )
    assert refused.json()["error"]["code"] == "model_unavailable"

    set_course(
        client,
        teacher,
        room.course_id,
        models={**NO_MODELS, "feedback": gpt(credential)},
    )
    llm.reply = MISTAKE
    submit(client, student, room.course_id)

    route = llm.routes[-1]
    assert (route.provider, route.model) == ("openai", "gpt-test")
    assert str(route.credential.id) == credential["id"]
    assert route.credential.api_key == KEY
    assert KEY not in repr(route)


def test_an_unknown_credential_cannot_be_chosen(client, teacher) -> None:
    course = create_course(client, teacher)
    fake = {"provider": "openai", "model": "gpt-test", "credential_id": NO_ID}

    response = client.put(
        course_path(course["id"]),
        headers=teacher.headers,
        json={"models": {**NO_MODELS, "tutor": fake}},
    )

    assert response.json()["error"]["code"] == "credential_unavailable"


NO_ID = "00000000-0000-4000-8000-000000000000"


def test_withdrawing_a_model_resets_the_courses_using_it(client, admin, teacher):
    credential = add_study(client, admin)
    course = create_course(client, teacher)
    set_course(
        client, teacher, course["id"], models={**NO_MODELS, "feedback": gpt(credential)}
    )

    client.patch(
        f"{ADMIN}/{credential['id']}",
        headers=admin.headers,
        json={"offered_models": ["gpt-mini"]},
    )

    body = client.get(course_path(course["id"]), headers=teacher.headers).json()
    assert body["course"]["models"]["feedback"] is None
    assert body["effective"]["models"]["feedback"]["origin"] == "server"
    assert body["notices"] == [
        {
            "task": "feedback",
            "model": "gpt-test",
            "reason": "model_withdrawn",
            "at": body["notices"][0]["at"],
        }
    ]
    assert set_course(client, teacher, course["id"])["notices"] == []


def test_deleting_a_key_erases_it_and_resets_its_courses(client, db, admin, teacher):
    credential = add_study(client, admin)
    course = create_course(client, teacher)
    set_course(
        client, teacher, course["id"], models={**NO_MODELS, "tutor": gpt(credential)}
    )

    response = client.delete(f"{ADMIN}/{credential['id']}", headers=admin.headers)

    assert response.status_code == 204
    assert db.scalar(select(LLMCredential.id)) is None
    body = client.get(course_path(course["id"]), headers=teacher.headers).json()
    assert body["course"]["models"]["tutor"] is None
    assert body["notices"][0]["reason"] == "credential_removed"


def test_teachers_add_their_own_key_only_if_allowed(
    client, admin, teacher, other_teacher
) -> None:
    course = create_course(client, teacher)
    other = create_course(client, teacher, name="Geometría")

    refused = client.post(own_path(course["id"]), headers=teacher.headers, json=OPENAI)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "teacher_keys_disabled"

    allow_teacher_keys(client, admin)
    assert client.get(course_path(course["id"]), headers=teacher.headers).json()[
        "allow_teacher_keys"
    ]
    response = client.post(own_path(course["id"]), headers=teacher.headers, json=OPENAI)
    assert response.status_code == 201, response.text
    own = response.json()
    assert own["scope"] == "course" and own["key_hint"] == "…cdef"
    assert own["id"] in sources(client, teacher, course["id"])
    assert own["id"] not in sources(client, teacher, other["id"])
    listed = client.get(own_path(course["id"]), headers=teacher.headers).json()
    assert [c["id"] for c in listed] == [own["id"]]
    assert (
        client.get(own_path(course["id"]), headers=other_teacher.headers).status_code
        == 404
    )
    assert (
        client.delete(
            f"{own_path(other['id'])}/{own['id']}", headers=teacher.headers
        ).status_code
        == 404
    )


def test_turning_teacher_keys_off_resets_the_tasks_using_them(
    client, admin, teacher
) -> None:
    course = create_course(client, teacher)
    allow_teacher_keys(client, admin)
    own = client.post(
        own_path(course["id"]), headers=teacher.headers, json=OPENAI
    ).json()
    set_course(client, teacher, course["id"], models={**NO_MODELS, "review": gpt(own)})

    allow_teacher_keys(client, admin, allowed=False)

    body = client.get(course_path(course["id"]), headers=teacher.headers).json()
    assert body["course"]["models"]["review"] is None
    assert body["notices"][0]["reason"] == "teacher_keys_disabled"
    assert own["id"] not in sources(client, teacher, course["id"])


def test_a_teacher_deletes_their_key(client, db, admin, teacher) -> None:
    course = create_course(client, teacher)
    allow_teacher_keys(client, admin)
    own = client.post(
        own_path(course["id"]), headers=teacher.headers, json=OPENAI
    ).json()

    response = client.delete(
        f"{own_path(course['id'])}/{own['id']}", headers=teacher.headers
    )

    assert response.status_code == 204
    assert db.scalar(select(LLMCredential.id)) is None


def test_the_admin_sees_every_model_of_a_key(client, admin) -> None:
    credential = add_study(client, admin)
    client.patch(
        f"{ADMIN}/{credential['id']}",
        headers=admin.headers,
        json={"offered_models": ["gpt-test"]},
    )

    body = client.get(f"{ADMIN}/{credential['id']}/models", headers=admin.headers)

    assert body.status_code == 200
    assert [m["id"] for m in body.json()["models"]] == ["gpt-mini", "gpt-test"]


def test_roles(client, admin, teacher, student) -> None:
    credential = add_study(client, admin)
    course = create_course(client, teacher)

    assert client.get(ADMIN, headers=teacher.headers).status_code == 403
    assert (
        client.delete(
            f"{ADMIN}/{credential['id']}", headers=teacher.headers
        ).status_code
        == 403
    )
    assert (
        client.get(own_path(course["id"]), headers=student.headers).status_code == 403
    )


def test_keys_never_reach_logs_or_the_study_export(
    client, admin, teacher, student, llm, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    credential = add_study(client, admin)
    room = classroom(client, teacher, student)
    set_course(
        client,
        teacher,
        room.course_id,
        models={**NO_MODELS, "feedback": gpt(credential)},
    )
    llm.reply = MISTAKE
    submit(client, student, room.course_id)
    llm.fail_chat = True
    submit(client, student, room.course_id)

    assert KEY not in caplog.text
    assert KEY.encode() not in export(client, admin).content


def test_the_credentials_table_is_closed_to_clients(db) -> None:
    rows = db.execute(
        text(
            "select grantee from information_schema.role_table_grants "
            "where table_name = 'llm_credentials' "
            "and grantee in ('anon', 'authenticated')"
        )
    ).all()
    assert rows == []
