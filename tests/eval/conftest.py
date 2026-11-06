"""Fixtures for the evaluation (specs/009, specs/017): the real model, not the fake."""

import hashlib
import json
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.llm.client import ChatResult, LLMClient, get_llm
from tests.eval.subjects import CACHE


class EvalLLM:
    """The configured client, timing each chat call by task and keeping embeddings on
    disk, so each material is embedded once per embedding model rather than per run."""

    def __init__(self, inner: LLMClient, cache: Path) -> None:
        self._inner = inner
        self._cache_path = cache
        self._cache: dict[str, list[float]] = (
            json.loads(cache.read_text()) if cache.exists() else {}
        )
        self._dirty = False
        self.calls: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        # Provider failures and timeouts (LLM_TIMEOUT_SECONDS), by task.
        self.errors: dict[str, int] = defaultdict(int)

    @property
    def chat_model(self) -> str:
        return self._inner.chat_model

    def chat_json(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        task="tutor",
    ) -> ChatResult:
        started = time.perf_counter()
        try:
            result = self._inner.chat_json(system, messages, temperature, task)
        except Exception:
            self.errors[task] += 1
            raise
        elapsed = (time.perf_counter() - started) * 1000
        self.calls[task].append((elapsed, not result.data))
        return result

    def embed(self, texts: list[str]) -> list[list[float]]:
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        missing = [t for t, k in zip(texts, keys, strict=True) if k not in self._cache]
        if missing:
            vectors = self._inner.embed(missing)
            for text, vector in zip(missing, vectors, strict=True):
                self._cache[hashlib.sha256(text.encode()).hexdigest()] = vector
            self._dirty = True
        return [self._cache[k] for k in keys]

    def is_reachable(self) -> bool:
        return self._inner.is_reachable()

    def save(self) -> None:
        if self._dirty:
            CACHE.mkdir(exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache))

    def latency(self, task: str) -> dict:
        calls = self.calls.get(task, [])
        return {
            "calls": len(calls),
            "median_ms": round(statistics.median(c[0] for c in calls))
            if calls
            else None,
            "unusable_replies": sum(c[1] for c in calls),
            "errors": self.errors.get(task, 0),
        }


@pytest.fixture
def llm():
    # The real model and the production thresholds, not the test ones.
    os.environ["RETRIEVAL_MIN_SIMILARITY"] = "0.55"
    os.environ["RETRIEVAL_MIN_SIMILARITY_EXERCISES"] = "0.40"
    os.environ["DAILY_MESSAGE_LIMIT"] = "1000"
    get_settings.cache_clear()
    settings = get_settings()
    name = settings.llm_embedding_model.replace(":", "-").replace("/", "-")
    client = EvalLLM(get_llm(), CACHE / f"embeddings-{name}.json")
    yield client
    client.save()
    get_settings.cache_clear()
