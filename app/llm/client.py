"""Single entry point for chat and embedding calls (constitution V, research R1)."""

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from openai import OpenAI, OpenAIError

from app.core.config import Settings, get_settings


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

    def chat_json(self, system: str, messages: list[dict[str, str]]) -> ChatResult: ...

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

    def chat_json(self, system: str, messages: list[dict[str, str]]) -> ChatResult:
        try:
            response = self._client.chat.completions.create(
                model=self._settings.llm_chat_model,
                messages=[{"role": "system", "content": system}, *messages],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        content = response.choices[0].message.content or ""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
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
