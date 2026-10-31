"""Model providers per task (spec 014): settings, routing, adapters, cost per model."""

from types import SimpleNamespace

import anthropic
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.client import (
    AnthropicProvider,
    ChatResult,
    LLMError,
    LLMRouter,
    OpenAICompatProvider,
    parse_json_reply,
)
from app.services.interactions import estimate_cost

ENV = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_CHAT_MODEL",
    "LLM_BASE_URL",
    "OLLAMA_BASE_URL",
    "LLM_EMBEDDING_PROVIDER",
    "LLM_FEEDBACK_PROVIDER",
    "LLM_FEEDBACK_MODEL",
    "LLM_FEEDBACK_EFFORT",
    "LLM_PRICES",
)


@pytest.fixture
def env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)

    def make(**values: str) -> Settings:
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        return Settings(_env_file=None)

    return make


# --- Settings and routing ----------------------------------------------------------


def test_by_default_every_task_runs_on_local_ollama(env) -> None:
    settings = env()

    for task in ("tutor", "feedback", "review", "questions"):
        route = settings.route(task)
        assert (route.provider, route.model, route.effort) == (
            "ollama",
            "qwen2.5:7b",
            None,
        )
    assert settings.ollama_base_url == "http://localhost:11434/v1"


def test_a_task_overrides_the_default_provider_model_and_effort(env) -> None:
    settings = env(
        LLM_PROVIDER="anthropic",
        LLM_MODEL="claude-haiku-5-5",
        LLM_FEEDBACK_PROVIDER="openai",
        LLM_FEEDBACK_MODEL="gpt-test",
        LLM_FEEDBACK_EFFORT="low",
    )

    assert settings.route("tutor") == ("anthropic", "claude-haiku-5-5", None)
    assert settings.route("feedback") == ("openai", "gpt-test", "low")


def test_the_old_variable_names_keep_working(env) -> None:
    settings = env(LLM_CHAT_MODEL="qwen2.5:3b", LLM_BASE_URL="http://gpu:11434/v1")

    assert settings.route("tutor").model == "qwen2.5:3b"
    assert settings.ollama_base_url == "http://gpu:11434/v1"


def test_anthropic_cannot_make_embeddings(env) -> None:
    with pytest.raises(ValidationError):
        env(LLM_EMBEDDING_PROVIDER="anthropic")


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete_json(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        return ChatResult({"ok": True}, kwargs["model"], 1, 1)

    def is_reachable(self, model: str) -> bool:
        return True


def test_the_router_sends_each_task_to_its_provider(env) -> None:
    settings = env(
        LLM_FEEDBACK_PROVIDER="anthropic",
        LLM_FEEDBACK_MODEL="claude-sonnet-5-5",
        LLM_FEEDBACK_EFFORT="low",
    )
    ollama, claude = FakeProvider(), FakeProvider()
    router = LLMRouter(settings, providers={"ollama": ollama, "anthropic": claude})

    tutor = router.chat_json("sys", [{"role": "user", "content": "hola"}])
    feedback = router.chat_json("sys", [], temperature=0.0, task="feedback")

    assert tutor.model == "qwen2.5:7b" and ollama.calls[0]["temperature"] == 0.2
    assert feedback.model == "claude-sonnet-5-5"
    assert claude.calls[0]["effort"] == "low" and claude.calls[0]["temperature"] == 0.0


# --- Anthropic ---------------------------------------------------------------------


def message(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop_reason,
        model="claude-haiku-5-5",
        usage=SimpleNamespace(input_tokens=120, output_tokens=30),
    )


class FakeMessages:
    def __init__(self, reply=None, error: Exception | None = None) -> None:
        self.reply, self.error, self.calls = reply, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.reply


def fake_anthropic(reply=None, error=None):
    messages, beta = FakeMessages(reply, error), FakeMessages(reply, error)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=beta))


def test_anthropic_gets_the_system_prompt_and_no_temperature() -> None:
    client = fake_anthropic(message('```json\n{"kind": "answer", "text": "Hola"}\n```'))
    provider = AnthropicProvider(client=client, max_tokens=16000, fallbacks="")

    result = provider.complete_json(
        model="claude-haiku-5-5",
        system="Eres el tutor.",
        messages=[{"role": "user", "content": "¿Qué es x?"}],
        temperature=0.0,
        effort="low",
    )

    [call] = client.messages.calls
    assert "temperature" not in call
    assert call["system"] == "Eres el tutor."
    assert call["output_config"] == {"effort": "low"}
    assert call["messages"] == [{"role": "user", "content": "¿Qué es x?"}]
    assert result == ChatResult(
        {"kind": "answer", "text": "Hola"}, "claude-haiku-5-5", 120, 30
    )


def test_anthropic_refusals_and_errors_are_llm_errors() -> None:
    refused = AnthropicProvider(
        client=fake_anthropic(message("", stop_reason="refusal")),
        max_tokens=16000,
        fallbacks="",
    )
    failing = AnthropicProvider(
        client=fake_anthropic(error=anthropic.AnthropicError("down")),
        max_tokens=16000,
        fallbacks="",
    )

    for provider in (refused, failing):
        with pytest.raises(LLMError):
            provider.complete_json(
                model="claude-haiku-5-5", system="s", messages=[], temperature=0.2
            )


def test_anthropic_fallbacks_only_on_models_that_support_them() -> None:
    client = fake_anthropic(message("{}"))
    provider = AnthropicProvider(client=client, max_tokens=16000, fallbacks="default")

    for model in ("claude-opus-5-5", "claude-haiku-5-5"):
        provider.complete_json(model=model, system="s", messages=[], temperature=0.2)

    [beta] = client.beta.messages.calls
    assert beta["model"] == "claude-opus-5-5" and beta["fallbacks"] == "default"
    assert beta["betas"] == ["server-side-fallback-2026-07-01"]
    assert [c["model"] for c in client.messages.calls] == ["claude-haiku-5-5"]


# --- OpenAI-compatible -------------------------------------------------------------


def test_openai_compatible_keeps_json_mode_and_temperature() -> None:
    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"a": 1}'))],
        model="gpt-test",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
    )
    completions = FakeMessages(reply)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = OpenAICompatProvider(client=client)

    result = provider.complete_json(
        model="gpt-test", system="s", messages=[], temperature=0.0, effort="low"
    )

    [call] = completions.calls
    assert call["temperature"] == 0.0
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0] == {"role": "system", "content": "s"}
    assert result == ChatResult({"a": 1}, "gpt-test", 10, 2)


# --- Replies and cost --------------------------------------------------------------


def test_json_replies_wrapped_in_text_or_fences_are_read() -> None:
    assert parse_json_reply('Aquí tienes:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Respuesta: {"a": {"b": 2}} fin') == {"a": {"b": 2}}


def test_cost_uses_the_price_of_the_model_that_answered(env) -> None:
    settings = env(LLM_PRICES='{"gpt-test": [1.0, 2.0]}')

    haiku = estimate_cost(settings, 1_000_000, 1_000_000, "claude-haiku-5-5")
    custom = estimate_cost(settings, 1_000_000, 1_000_000, "gpt-test")
    local = estimate_cost(settings, 1_000_000, 1_000_000, "qwen2.5:7b")

    assert (float(haiku), float(custom), float(local)) == (0.6, 3.0, 0.0)
