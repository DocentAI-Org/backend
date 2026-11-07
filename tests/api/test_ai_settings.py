"""US2, US6 (spec 019) — AI settings: the server's, the study's and each course's; the
model for each task; the models the teacher can choose from."""

import pytest

from app.core.config import Route, get_settings
from tests.api.helpers import COVERED_QUESTION, ask, classroom, open_conversation
from tests.api.test_us2_courses import create_course
from tests.api.test_us7_exercises import MISTAKE, submit

ADMIN = "/v1/admin/ai-settings"
TASKS = ("tutor", "feedback", "review", "questions")
SERVER_LIMITS = {
    "messages": None,
    "period": "day",
    "counted_tasks": ["tutor", "feedback", "review"],
}
SERVER_RETRIEVAL = {
    "top_k": 4,
    "min_similarity": 0.2,
    "min_similarity_exercises": 0.2,
    "history_messages": 6,
}
NO_MODELS = dict.fromkeys(TASKS)
QWEN_3B = {
    "provider": "ollama",
    "model": "qwen2.5:3b",
    "temperature": 0.4,
    "effort": None,
    "max_tokens": 800,
}


def course_path(course_id: str) -> str:
    return f"/v1/teacher/courses/{course_id}/ai-settings"


def server_model(task: str) -> dict:
    route = get_settings().route(task)
    return {
        "provider": route.provider,
        "model": route.model,
        "temperature": None,
        "effort": route.effort,
        "max_tokens": None,
        "origin": "server",
    }


def set_course(client, teacher, course_id: str, **groups):
    body = {"models": NO_MODELS, "limits": None, "retrieval": None, **groups}
    response = client.put(course_path(course_id), headers=teacher.headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def set_study(client, admin, **groups):
    body = {
        "models": NO_MODELS,
        "limits": None,
        "retrieval": None,
        "ceiling": None,
        **groups,
    }
    response = client.put(ADMIN, headers=admin.headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_without_changes_the_servers_values_apply(client, admin) -> None:
    body = client.get(ADMIN, headers=admin.headers).json()

    assert body["study"] == {
        "models": NO_MODELS,
        "limits": None,
        "retrieval": None,
        "ceiling": None,
    }
    assert body["server"] == body["effective"]
    effective = body["effective"]
    assert effective["limits"] == SERVER_LIMITS
    assert effective["retrieval"] == SERVER_RETRIEVAL
    assert effective["ceiling"] == {"messages": 5}
    assert effective["models"] == {task: server_model(task) for task in TASKS}


def test_the_admin_sets_the_study_values_for_every_course(
    client, admin, teacher
) -> None:
    course = create_course(client, teacher)
    limits = {"messages": 40, "period": "week", "counted_tasks": ["tutor"]}

    body = set_study(
        client,
        admin,
        models={**NO_MODELS, "tutor": QWEN_3B},
        limits=limits,
        ceiling={"messages": None},
    )

    assert body["effective"]["limits"] == limits
    assert body["effective"]["ceiling"] == {"messages": None}
    assert body["effective"]["models"]["tutor"] == {**QWEN_3B, "origin": "study"}
    seen = client.get(course_path(course["id"]), headers=teacher.headers).json()
    assert seen["effective"]["limits"] == limits
    assert seen["effective"]["models"]["tutor"]["origin"] == "study"
    assert seen["effective"]["models"]["feedback"] == server_model("feedback")
    assert seen["course"] == {"models": NO_MODELS, "limits": None, "retrieval": None}
    assert seen["ceiling"] == {"messages": None}


def test_a_teacher_changes_only_their_course(client, teacher) -> None:
    course = create_course(client, teacher)
    other = create_course(client, teacher, name="Geometría")
    limits = {"messages": 20, "period": "course", "counted_tasks": ["tutor", "review"]}
    retrieval = {**SERVER_RETRIEVAL, "top_k": 6}

    body = set_course(
        client,
        teacher,
        course["id"],
        models={**NO_MODELS, "feedback": QWEN_3B},
        limits=limits,
        retrieval=retrieval,
    )

    assert body["effective"]["limits"] == limits
    assert body["effective"]["retrieval"] == retrieval
    assert body["effective"]["models"]["feedback"] == {**QWEN_3B, "origin": "course"}
    assert body["inherited"]["limits"] == SERVER_LIMITS
    untouched = client.get(course_path(other["id"]), headers=teacher.headers).json()
    assert untouched["effective"] == untouched["inherited"]


def test_null_goes_back_to_the_inherited_values(client, teacher) -> None:
    course = create_course(client, teacher)
    set_course(
        client,
        teacher,
        course["id"],
        models={**NO_MODELS, "tutor": QWEN_3B},
        limits={"messages": 3, "period": "day", "counted_tasks": ["tutor"]},
    )

    body = set_course(client, teacher, course["id"])

    assert body["effective"] == body["inherited"]


@pytest.mark.parametrize(
    "groups",
    [
        {"limits": {**SERVER_LIMITS, "messages": 0}},
        {"limits": {**SERVER_LIMITS, "period": "month"}},
        {"limits": {**SERVER_LIMITS, "counted_tasks": ["questions"]}},
        {"retrieval": {**SERVER_RETRIEVAL, "top_k": 0}},
        {"retrieval": {**SERVER_RETRIEVAL, "min_similarity": 1.5}},
        {"retrieval": {**SERVER_RETRIEVAL, "history_messages": 21}},
        {"models": {**NO_MODELS, "tutor": {**QWEN_3B, "temperature": 3}}},
        {"models": {**NO_MODELS, "tutor": {**QWEN_3B, "max_tokens": 10}}},
    ],
)
def test_invalid_values_are_rejected(client, admin, teacher, groups) -> None:
    course = create_course(client, teacher)
    body = {"models": NO_MODELS, **groups}

    assert client.put(ADMIN, headers=admin.headers, json=body).status_code == 422
    assert (
        client.put(
            course_path(course["id"]), headers=teacher.headers, json=body
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    ("choice", "code"),
    [
        ({**QWEN_3B, "model": "llama9:70b"}, "model_unavailable"),
        ({**QWEN_3B, "provider": "openai", "model": "gpt-x"}, "provider_unavailable"),
        (
            {**QWEN_3B, "provider": "anthropic", "model": "claude-haiku-5-5"},
            "temperature_not_supported",
        ),
    ],
)
def test_only_models_the_server_offers_are_saved(
    client, admin, teacher, choice, code
) -> None:
    course = create_course(client, teacher)
    body = {"models": {**NO_MODELS, "feedback": choice}}

    for path, user in ((ADMIN, admin), (course_path(course["id"]), teacher)):
        response = client.put(path, headers=user.headers, json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == code


def test_a_model_cannot_be_saved_while_its_source_is_unreachable(
    client, teacher, catalog
) -> None:
    course = create_course(client, teacher)
    catalog.by_provider["ollama"].reachable = False

    response = client.put(
        course_path(course["id"]),
        headers=teacher.headers,
        json={"models": {**NO_MODELS, "tutor": QWEN_3B}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "provider_unreachable"


def test_anthropic_takes_effort_but_no_temperature(client, teacher) -> None:
    course = create_course(client, teacher)
    claude = {
        "provider": "anthropic",
        "model": "claude-haiku-5-5",
        "temperature": None,
        "effort": "low",
        "max_tokens": None,
    }

    body = set_course(
        client, teacher, course["id"], models={**NO_MODELS, "questions": claude}
    )

    assert body["effective"]["models"]["questions"] == {**claude, "origin": "course"}


def test_the_teacher_lists_the_models_they_can_choose(
    client, admin, teacher, catalog
) -> None:
    course = create_course(client, teacher)
    catalog.by_provider["anthropic"].reachable = False

    for path, user in (
        (f"/v1/teacher/courses/{course['id']}/ai-models", teacher),
        ("/v1/admin/ai-models", admin),
    ):
        body = client.get(path, headers=user.headers).json()
        sources = {s["provider"]: s for s in body["sources"]}
        assert set(sources) == {"ollama", "anthropic"}
        assert [m["id"] for m in sources["ollama"]["models"]] == [
            "gemma4:e4b-it-qat",
            "qwen2.5:3b",
            "qwen2.5:7b",
        ]
        assert sources["ollama"]["models"][1]["parameter_size"] == "3.1B"
        assert sources["anthropic"]["reachable"] is False


def test_roles(client, teacher, other_teacher, student) -> None:
    course = create_course(client, teacher)

    assert client.get(ADMIN, headers=teacher.headers).status_code == 403
    assert client.get("/v1/admin/ai-models", headers=teacher.headers).status_code == 403
    models = f"/v1/teacher/courses/{course['id']}/ai-models"
    for path in (course_path(course["id"]), models):
        assert client.get(path, headers=other_teacher.headers).status_code == 404
        assert client.get(path, headers=student.headers).status_code == 403


def test_each_task_uses_the_model_of_its_course(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    set_course(
        client, teacher, room.course_id, models={**NO_MODELS, "feedback": QWEN_3B}
    )
    conversation = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    llm.reply = MISTAKE
    submit(client, student, room.course_id)

    tutor = get_settings().route("tutor")
    assert llm.tasks == ["tutor", "feedback"]
    assert llm.routes == [
        Route(tutor.provider, tutor.model, tutor.effort),
        Route("ollama", "qwen2.5:3b", None, 0.4, 800),
    ]


def test_the_course_retrieval_settings_apply(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    set_course(
        client,
        teacher,
        room.course_id,
        retrieval={**SERVER_RETRIEVAL, "history_messages": 0},
    )

    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    assert len(llm.chat_calls[-1][1]) == 1  # no earlier messages

    set_course(
        client,
        teacher,
        room.course_id,
        retrieval={**SERVER_RETRIEVAL, "min_similarity": 0.99},
    )
    calls = len(llm.chat_calls)
    reply = ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    assert reply.json()["tutor_message"]["kind"] == "no_source"
    assert len(llm.chat_calls) == calls
