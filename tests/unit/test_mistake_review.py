"""Validation of the model's mistake review (spec 005 FR-004)."""

from app.services.reviews import validate_review

REPLY = {
    "explanation": "El número de fuera multiplica a cada término (F1).",
    "worked_example": "3(x + 2) = 3x + 6.",
    "practice": ["4(x - 1) = 8", "2(x + 5) = 14", "Uno más"],
    "cited": ["F1", "f2"],
}


def test_a_grounded_reply_is_accepted_and_trimmed() -> None:
    review = validate_review(REPLY, fragment_count=2)
    assert review is not None
    assert review.cited_indexes == [0, 1]
    assert review.practice == ["4(x - 1) = 8", "2(x + 5) = 14"]
    assert "F1" not in review.explanation
    assert review.worked_example == "3(x + 2) = 3x + 6."


def test_replies_without_grounding_or_explanation_are_rejected() -> None:
    assert validate_review(REPLY | {"cited": ["F5"]}, fragment_count=2) is None
    assert validate_review(REPLY | {"cited": "F1"}, fragment_count=2) is None
    assert validate_review(REPLY | {"explanation": " "}, fragment_count=2) is None


def test_practice_needs_at_least_one_statement() -> None:
    assert validate_review(REPLY | {"practice": []}, fragment_count=2) is None
    assert validate_review(REPLY | {"practice": [" ", 3]}, fragment_count=2) is None
    one = validate_review(REPLY | {"practice": ["Solo uno", ""]}, fragment_count=2)
    assert one is not None and one.practice == ["Solo uno"]


def test_the_worked_example_is_optional() -> None:
    review = validate_review(REPLY | {"worked_example": None}, fragment_count=2)
    assert review is not None and review.worked_example is None
