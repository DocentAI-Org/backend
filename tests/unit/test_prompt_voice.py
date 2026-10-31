"""Texts the student reads speak to them, not about them (end-to-end review)."""

import pytest

from app.llm.prompts import load_prompt


@pytest.mark.parametrize("name", ["exercise_feedback", "mistake_review"])
def test_the_explanation_speaks_to_the_student(name: str) -> None:
    prompt = load_prompt(name, "es")

    assert "háblale de tú" in prompt.lower()
    assert "«el estudiante»" in prompt.lower()
