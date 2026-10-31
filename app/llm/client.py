"""Single entry point for chat and embedding calls (constitution V, research R1), with a
provider and model per task (specs/014): Ollama, OpenAI-compatible APIs, Anthropic."""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import anthropic
from openai import OpenAI, OpenAIError

from app.core.config import Effort, Provider, Settings, Task, get_settings

# A valid JSON escape, or a lone backslash: models write LaTeX (\sqrt, \() unescaped.
_ESCAPE = re.compile(r'(\\(?:u[0-9a-fA-F]{4}|["\\/bfnrt]))|\\', re.S)
# Math delimiters only; `$` is common in prices (spec 010 FR-002).
_MATH = re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]", re.S)
# \frac, \times, \neq, \rightarrow, \beta read as JSON escapes.
_ESCAPED_COMMAND = re.compile(r"[\b\f\n\r\t](?=[a-zA-Z])")
_COMMAND_LETTER = {"\b": "b", "\f": "f", "\n": "n", "\r": "r", "\t": "t"}


# Form feed and backspace never appear in real text, so outside math too.
_ESCAPED_COMMAND_ANYWHERE = re.compile(r"[\b\f](?=[a-zA-Z])")


def _command(match: re.Match[str]) -> str:
    return "\\" + _COMMAND_LETTER[match.group(0)]


def _restore_math(value: Any) -> Any:
    if isinstance(value, str):
        value = _MATH.sub(lambda m: _ESCAPED_COMMAND.sub(_command, m.group(0)), value)
        return _ESCAPED_COMMAND_ANYWHERE.sub(_command, value)
    if isinstance(value, list):
        return [_restore_math(item) for item in value]
    if isinstance(value, dict):
        return {key: _restore_math(item) for key, item in value.items()}
    return value


def _json_object(content: str) -> Any:
    try:
        return json.loads(_ESCAPE.sub(lambda m: m.group(1) or "\\\\", content))
    except json.JSONDecodeError:
        return None


def parse_json_reply(content: str) -> dict[str, Any]:
    """The model's JSON object, keeping its LaTeX (spec 010); {} if unusable. Models
    without a JSON mode may wrap it in a code fence or a sentence (spec 014)."""
    data = _json_object(content)
    if data is None and "{" in content:
        data = _json_object(content[content.index("{") : content.rindex("}") + 1])
    return _restore_math(data) if isinstance(data, dict) else {}


class LLMError(Exception):
    """The provider failed, timed out, refused or returned an unusable response."""


@dataclass(frozen=True)
class ChatResult:
    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    @property
    def chat_model(self) -> str: ...

    def chat_json(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        task: Task = "tutor",
    ) -> ChatResult: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def is_reachable(self) -> bool: ...


class ChatProvider(Protocol):
    def complete_json(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        temperature: float,
        effort: Effort | None = None,
    ) -> ChatResult: ...

    def is_reachable(self, model: str) -> bool: ...


class OpenAICompatProvider:
    """Ollama, OpenAI or any OpenAI-compatible API (Mistral, vLLM...)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def complete_json(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        temperature: float,
        effort: Effort | None = None,
    ) -> ChatResult:
        # `effort` is Anthropic's; these models get the temperature instead.
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, *messages],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
        except OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        if not response.choices:
            raise LLMError("The provider returned no choices.")
        usage = response.usage
        return ChatResult(
            data=parse_json_reply(response.choices[0].message.content or ""),
            model=response.model or model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    def embed(self, model: str, texts: list[str], dimensions: int | None) -> list:
        extra = {"dimensions": dimensions} if dimensions else {}
        try:
            response = self._client.embeddings.create(model=model, input=texts, **extra)
        except OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]

    def is_reachable(self, model: str) -> bool:
        try:
            self._client.models.list(timeout=3)
            return True
        except OpenAIError:
            return False


# Claude models with a server-side fallback when they decline (Claude API).
_FALLBACK_MODELS = {
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    """Claude through the Messages API. No temperature (rejected since 2026-10-21) and
    no prefill: the prompts ask for JSON and the reply is read tolerantly."""

    def __init__(self, client: Any, max_tokens: int, fallbacks: str) -> None:
        self._client = client
        self._max_tokens = max_tokens
        self._fallbacks = fallbacks

    def complete_json(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        temperature: float,
        effort: Effort | None = None,
    ) -> ChatResult:
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": messages,
        }
        if effort:
            request["output_config"] = {"effort": effort}
        try:
            if self._fallbacks and model in _FALLBACK_MODELS:
                response = self._client.beta.messages.create(
                    betas=[_FALLBACK_BETA], fallbacks=self._fallbacks, **request
                )
            else:
                response = self._client.messages.create(**request)
        except anthropic.AnthropicError as exc:
            raise LLMError(str(exc)) from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined the request.")
        text = "".join(b.text for b in response.content if b.type == "text")
        return ChatResult(
            data=parse_json_reply(text),
            model=response.model or model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def is_reachable(self, model: str) -> bool:
        try:
            self._client.models.retrieve(model, timeout=3)
            return True
        except anthropic.AnthropicError:
            return False


def _provider(settings: Settings, name: Provider) -> Any:
    if name == "anthropic":
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,  # None: the SDK reads the environment
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
        return AnthropicProvider(
            client, settings.llm_max_tokens, settings.llm_anthropic_fallbacks
        )
    base_url, api_key = (
        (settings.openai_base_url, settings.openai_api_key)
        if name == "openai"
        else (settings.ollama_base_url, settings.ollama_api_key)
    )
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    return OpenAICompatProvider(client)


class LLMRouter:
    """The app's LLMClient: each task goes to its provider and model (specs/014)."""

    def __init__(
        self, settings: Settings, providers: dict[str, Any] | None = None
    ) -> None:
        self._settings = settings
        self._providers: dict[str, Any] = dict(providers or {})

    def _get(self, name: Provider) -> Any:
        if name not in self._providers:
            self._providers[name] = _provider(self._settings, name)
        return self._providers[name]

    @property
    def chat_model(self) -> str:
        return self._settings.route("tutor").model

    def chat_json(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        task: Task = "tutor",
    ) -> ChatResult:
        route = self._settings.route(task)
        return self._get(route.provider).complete_json(
            model=route.model,
            system=system,
            messages=messages,
            temperature=temperature,
            effort=route.effort,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        settings = self._settings
        provider = settings.llm_embedding_provider
        expected = settings.embedding_dimensions
        vectors = self._get(provider).embed(
            settings.llm_embedding_model,
            texts,
            expected if provider == "openai" else None,
        )
        if any(len(vector) != expected for vector in vectors):
            raise LLMError(
                f"Embedding model returned vectors that are not {expected}-dimensional."
            )
        return vectors

    def is_reachable(self) -> bool:
        route = self._settings.route("tutor")
        return self._get(route.provider).is_reachable(route.model)


@lru_cache
def _default_client() -> LLMRouter:
    return LLMRouter(get_settings())


def get_llm() -> LLMClient:
    return _default_client()
