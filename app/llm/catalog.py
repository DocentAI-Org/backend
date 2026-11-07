"""The models each configured provider offers (specs/019): Ollama's installed models,
the models of the server's OpenAI and Anthropic accounts and those of each stored
credential, cached for a few minutes."""

import time
import uuid
from functools import lru_cache
from typing import Literal, Protocol

import anthropic
import httpx
from openai import OpenAI, OpenAIError

from app.core.config import Provider, Settings, get_settings
from app.llm.credentials import CredentialAccess
from app.schemas.ai_settings import ModelInfo, ModelSource

KeyCheck = Literal["ok", "rejected", "unreachable"]

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

    def check_key(self, credential: CredentialAccess) -> KeyCheck: ...

    def credential_models(self, credential: CredentialAccess) -> ModelSource:
        """Every model the credential's account offers."""
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


def _openai_models(base_url: str, api_key: str | None) -> list[ModelInfo]:
    client = OpenAI(
        base_url=base_url, api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0
    )
    return [ModelInfo(id=m.id) for m in client.models.list()]


def _anthropic_models(api_key: str | None) -> list[ModelInfo]:
    client = anthropic.Anthropic(
        api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0
    )
    return [
        ModelInfo(id=m.id, label=m.display_name) for m in client.models.list(limit=100)
    ]


def _openai(settings: Settings) -> list[ModelInfo]:
    return _openai_models(settings.openai_base_url, settings.openai_api_key)


def _anthropic(settings: Settings) -> list[ModelInfo]:
    return _anthropic_models(settings.anthropic_api_key)


def _credential_models(credential: CredentialAccess, settings: Settings) -> list:
    if credential.provider == "anthropic":
        return _anthropic_models(credential.api_key)
    return _openai_models(
        credential.base_url or settings.openai_base_url, credential.api_key
    )


class ModelCatalog:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[Provider, tuple[float, ModelSource]] = {}
        self._credential_cache: dict[uuid.UUID, tuple[float, ModelSource]] = {}

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

    def check_key(self, credential: CredentialAccess) -> KeyCheck:
        try:
            _credential_models(credential, self._settings)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            return "rejected"
        except OpenAIError as exc:
            status = getattr(exc, "status_code", None)
            return "rejected" if status in (401, 403) else "unreachable"
        except (anthropic.AnthropicError, httpx.HTTPError):
            return "unreachable"
        return "ok"

    def credential_models(self, credential: CredentialAccess) -> ModelSource:
        cached = self._credential_cache.get(credential.id)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        try:
            models = _credential_models(credential, self._settings)
        except (httpx.HTTPError, OpenAIError, anthropic.AnthropicError):
            return ModelSource(
                provider=credential.provider,
                label=credential.label,
                reachable=False,
                models=[],
                credential_id=credential.id,
            )
        source = ModelSource(
            provider=credential.provider,
            label=credential.label,
            reachable=True,
            models=sorted(models, key=lambda m: m.id),
            credential_id=credential.id,
        )
        self._credential_cache[credential.id] = (time.monotonic(), source)
        return source


@lru_cache
def _default_catalog() -> ModelCatalog:
    return ModelCatalog(get_settings())


def get_catalog() -> Catalog:
    return _default_catalog()
