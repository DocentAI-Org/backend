"""SC-002: every route × role × own/other's data. New routes are picked up from the
contract automatically and must declare a request body below if they need one."""

import uuid

import pytest

from tests.api.helpers import classroom
from tests.api.test_us7_exercises import EXERCISE

BODIES: dict[tuple[str, str], dict] = {
    ("patch", "/v1/me"): {"preferred_language": "es"},
    ("post", "/v1/admin/teachers"): {"email": "x@example.org", "display_name": "X"},
    ("post", "/v1/admin/students/pseudonymous"): {"count": 1},
    ("post", "/v1/teacher/courses"): {"name": "X"},
    ("patch", "/v1/teacher/courses/{course_id}"): {"name": "X"},
    ("patch", "/v1/teacher/courses/{course_id}/class-code"): {"active": False},
    ("put", "/v1/teacher/courses/{course_id}/tutor-settings"): {
        "level": "basic",
        "tone": "neutral",
        "solution_policy": "direct",
    },
    (
        "patch",
        "/v1/teacher/courses/{course_id}/documents/{document_id}/fragments/{fragment_id}",
    ): {"excluded": True},
    ("post", "/v1/teacher/courses/{course_id}/topics"): {"name": "X"},
    ("patch", "/v1/teacher/courses/{course_id}/topics/{topic_id}"): {"name": "X"},
    ("put", "/v1/teacher/courses/{course_id}/topics/order"): {"topic_ids": []},
    ("post", "/v1/teacher/courses/{course_id}/topic-assignments"): {
        "topic_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
    },
    (
        "patch",
        "/v1/teacher/courses/{course_id}/topic-assignments/{assignment_id}",
    ): {"status": "confirmed"},
    ("put", "/v1/teacher/courses/{course_id}/messages/{message_id}/flag"): {
        "category": "poor",
        "correction": "x",
    },
    ("put", "/v1/teacher/courses/{course_id}/submissions/{submission_id}/flag"): {
        "category": "poor",
        "correction": "x",
    },
    ("post", "/v1/student/enrolments"): {"class_code": "ZZZ-9999"},
    (
        "post",
        "/v1/student/courses/{course_id}/conversations/{conversation_id}/messages",
    ): {"text": "hola"},
    ("post", "/v1/student/courses/{course_id}/submissions"): EXERCISE,
}
UPLOADS = {("post", "/v1/teacher/courses/{course_id}/documents")}


def _operations(client) -> list[tuple[str, str, dict]]:
    schema = client.get("/openapi.json").json()
    return [
        (method, path, operation)
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
    ]


def _call(client, method: str, path: str, operation: dict, course_id: str, headers):
    url = path.replace("{course_id}", course_id)
    while "{" in url:
        start = url.index("{")
        url = url[:start] + str(uuid.uuid4()) + url[url.index("}") + 1 :]
    kwargs: dict = {"headers": headers}
    if (method, path) in UPLOADS:
        kwargs["files"] = {"file": ("x.md", b"# x\n\ntexto", "text/markdown")}
    elif "requestBody" in operation:
        assert (method, path) in BODIES, f"add a body for {method} {path}"
        kwargs["json"] = BODIES[(method, path)]
    return client.request(method, url, **kwargs)


@pytest.fixture
def setting(client, teacher, student):
    return classroom(client, teacher, student)


def test_every_protected_route_requires_a_token(client, setting) -> None:
    for method, path, operation in _operations(client):
        if path == "/v1/health":
            continue
        response = _call(client, method, path, operation, setting.course_id, {})
        assert response.status_code == 401, (method, path)


def test_role_routers_reject_every_other_role(
    client, setting, admin, teacher, student
) -> None:
    owners = {"/v1/admin/": admin, "/v1/teacher/": teacher, "/v1/student/": student}
    users = [admin, teacher, student]
    for method, path, operation in _operations(client):
        prefix = next((p for p in owners if path.startswith(p)), None)
        if prefix is None:
            continue
        for user in users:
            if user is owners[prefix]:
                continue
            response = _call(
                client, method, path, operation, setting.course_id, user.headers
            )
            assert response.status_code == 403, (method, path, user.role)


def test_course_routes_hide_other_tenants_data(
    client, setting, other_teacher, other_student
) -> None:
    for method, path, operation in _operations(client):
        if "{course_id}" not in path:
            continue
        if path.startswith("/v1/teacher/"):
            user = other_teacher
        elif path.startswith("/v1/student/"):
            user = other_student
        else:
            continue
        response = _call(
            client, method, path, operation, setting.course_id, user.headers
        )
        assert response.status_code == 404, (method, path, response.text)
