"""Single entry point for chat and embedding calls (constitution V, research R1)."""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from openai import OpenAI, OpenAIError

from app.core.config import Settings, get_settings

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


def parse_json_reply(content: str) -> dict[str, Any]:
    """The model's JSON object, keeping its LaTeX (spec 010); {} if unusable."""
    try:
        data = json.loads(_ESCAPE.sub(lambda m: m.group(1) or "\\\\", content))
    except json.JSONDecodeError:
        return {}
    return _restore_math(data) if isinstance(data, dict) else {}


class LLMError(Exception):
    """The provider failed, timed out or returned an unusable response."""


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
        self, system: str, messages: list[dict[str, str]], temperature: float = 0.2
    ) -> ChatResult: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def is_reachable(self) -> bool: ...


class OpenAICompatClient:
    """Any OpenAI-compatible provider: Ollama, OpenAI, Mistral, Gemini, vLLM..."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )

    @property
    def chat_model(self) -> str:
        return self._settings.llm_chat_model

    def chat_json(
        self, system: str, messages: list[dict[str, str]], temperature: float = 0.2
    ) -> ChatResult:
        try:
            response = self._client.chat.completions.create(
                model=self._settings.llm_chat_model,
                messages=[{"role": "system", "content": system}, *messages],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
        except OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        if not response.choices:
            raise LLMError("The provider returned no choices.")
        data = parse_json_reply(response.choices[0].message.content or "")
        usage = response.usage
        return ChatResult(
            data=data,
            model=response.model or self._settings.llm_chat_model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(
                model=self._settings.llm_embedding_model, input=texts
            )
        except OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        vectors = [
            item.embedding for item in sorted(response.data, key=lambda d: d.index)
        ]
        expected = self._settings.embedding_dimensions
        if any(len(vector) != expected for vector in vectors):
            raise LLMError(
                f"Embedding model returned vectors that are not {expected}-dimensional."
            )
        return vectors

    def is_reachable(self) -> bool:
        try:
            self._client.models.list(timeout=3)
            return True
        except OpenAIError:
            return False


@lru_cache
def _default_client() -> OpenAICompatClient:
    return OpenAICompatClient(get_settings())


def get_llm() -> LLMClient:
    return _default_client()
