"""Prompts live in app/prompts/<language>/ so other languages can be added (FR-055)."""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache
def load_prompt(name: str, language: str = "es") -> str:
    return (PROMPTS_DIR / language / f"{name}.md").read_text(encoding="utf-8")


@lru_cache
def load_labels(name: str, language: str = "es") -> dict[str, str]:
    """Reads `key: value` lines, e.g. the wording of each tutor setting."""
    labels: dict[str, str] = {}
    for line in load_prompt(name, language).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            labels[key.strip()] = value.strip()
    return labels
