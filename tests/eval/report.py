"""Shared report helpers for the evaluation tasks (specs/017)."""

import json
import os
from pathlib import Path

import pytest

from app.core.config import Task, get_settings
from tests.eval.subjects import Subject


def model_label(task: Task) -> str:
    route = get_settings().route(task)
    return f"{route.model} (effort {route.effort})" if route.effort else route.model


def write_results(name: str, model: str, payload: dict) -> None:
    """Saves an evaluation's results for scripts/eval_models.py when EVAL_OUT is set."""
    if out := os.environ.get("EVAL_OUT"):
        path = Path(out)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.json").write_text(
            json.dumps({"model": model, **payload}, ensure_ascii=False, indent=1)
        )


def rate(values: list[bool]) -> str:
    if not values:
        return "—"
    return f"{sum(values)}/{len(values)} ({100 * sum(values) / len(values):.0f} %)"


def share(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def available(subjects: list[Subject]) -> list[tuple[Subject, bytes]]:
    """The subjects whose material is at hand; skips the test when there is none."""
    found = [(s, content) for s in subjects if (content := s.material()) is not None]
    missing = [s.slug for s in subjects if s.material() is None]
    if missing:
        print(
            f"\nSkipped (material not fetched): {', '.join(missing)}. "
            "Run `uv run python scripts/eval_corpus.py`."
        )
    if not found:
        pytest.skip("No subject material available.")
    return found


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        *("| " + " | ".join(row) + " |" for row in rows),
    ]
