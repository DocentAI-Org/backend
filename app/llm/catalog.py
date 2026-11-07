"""The models each configured provider offers (specs/019): Ollama's installed models and
the models of the OpenAI and Anthropic accounts, cached for a few minutes."""

import time
from functools import lru_cache
from typing import Protocol

import anthropic
import httpx
from openai import OpenAI, OpenAIError

from app.core.config import Provider, Settings, get_settings
from app.schemas.ai_settings import ModelInfo, ModelSource

CACHE_SECONDS = 300
TIMEOUT_SECONDS = 5.0
LABELS: dict[Provider, str] = {
    "ollama": "Ollama (local)",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
}
# Ollama lists embedding models with the chat models.
_EMBEDDING_FAMILIES = {"bert", "nomic-bert"}


class Catalog(Protocol):
    def sources(self) -> list[ModelSource]: ...

    def source(self, provider: Provider) -> ModelSource | None:
        """The provider's models, or None when the server has no key for it."""
        ...


def _ollama(settings: Settings) -> list[ModelInfo]:
    root = settings.ollama_base_url.rstrip("/").removesuffix("/v1")
    response = httpx.get(f"{root}/api/tags", timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    models = []
    for item in response.json().get("models", []):
        details = item.get("details") or {}
        if details.get("family") in _EMBEDDING_FAMILIES or "embed" in item["name"]:
            continue
        models.append(
            ModelInfo(
                id=item["name"],
                size_bytes=item.get("size"),
                parameter_size=details.get("parameter_size"),
                family=details.get("family"),
            )
        )
    return models


def _openai(settings: Settings) -> list[ModelInfo]:
    client = OpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
    )
    return [ModelInfo(id=m.id) for m in client.models.list()]


def _anthropic(settings: Settings) -> list[ModelInfo]:
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key, timeout=TIMEOUT_SECONDS, max_retries=0
    )
    return [
        ModelInfo(id=m.id, label=m.display_name) for m in client.models.list(limit=100)
    ]


class ModelCatalog:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[Provider, tuple[float, ModelSource]] = {}

    def _configured(self) -> list[Provider]:
        providers: list[Provider] = ["ollama"]
        if self._settings.openai_api_key:
            providers.append("openai")
        if self._settings.anthropic_api_key:
            providers.append("anthropic")
        return providers

    def _fetch(self, provider: Provider) -> ModelSource:
        fetch = {"ollama": _ollama, "openai": _openai, "anthropic": _anthropic}
        try:
            models = fetch[provider](self._settings)
        except (httpx.HTTPError, OpenAIError, anthropic.AnthropicError, KeyError):
            return ModelSource(
                provider=provider, label=LABELS[provider], reachable=False, models=[]
            )
        return ModelSource(
            provider=provider,
            label=LABELS[provider],
            reachable=True,
            models=sorted(models, key=lambda m: m.id),
        )

    def source(self, provider: Provider) -> ModelSource | None:
        if provider not in self._configured():
            return None
        cached = self._cache.get(provider)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        source = self._fetch(provider)
        # An unreachable source is asked again on the next request.
        if source.reachable:
            self._cache[provider] = (time.monotonic(), source)
        return source

    def sources(self) -> list[ModelSource]:
        return [s for p in self._configured() if (s := self.source(p)) is not None]


@lru_cache
def _default_catalog() -> ModelCatalog:
    return ModelCatalog(get_settings())


def get_catalog() -> Catalog:
    return _default_catalog()
