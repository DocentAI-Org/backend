"""Validation of the model's exercise feedback (spec 003 FR-002)."""

from app.services.exercises import validate_feedback

CODES = {"procedural", "conceptual"}
REPLY = {
    "verdict": "incorrect",
    "mistake_location": "Paso 1",
    "error_type": "procedural",
    "topic": "T2",
    "explanation": "El 2 multiplica a cada término.",
    "cited": ["F1", "f2", "F1"],
}


def check(reply: dict, fragments: int = 2, topics: int = 2):
    return validate_feedback(reply, fragments, topics, CODES)


def test_a_well_formed_reply_is_accepted() -> None:
    feedback = check(REPLY)
    assert feedback is not None
    assert feedback.verdict == "incorrect"
    assert feedback.error_type == "procedural"
    assert feedback.topic_index == 1
    assert feedback.cited_indexes == [0, 1]
    assert feedback.mistake_location == "Paso 1"


def test_replies_without_grounding_or_with_an_unknown_verdict_are_rejected() -> None:
    assert check({**REPLY, "cited": ["F5"]}) is None
    assert check({**REPLY, "cited": "F1"}) is None
    assert check({**REPLY, "verdict": "maybe"}) is None
    assert check({**REPLY, "verdict": "not_assessed"}) is None
    assert check({**REPLY, "explanation": "  "}) is None
    assert check({}) is None


def test_unknown_error_types_and_topics_are_dropped() -> None:
    feedback = check({**REPLY, "error_type": "typo", "topic": "T9"})
    assert feedback is not None
    assert feedback.error_type is None and feedback.unclassified is True
    assert feedback.topic_index is None


def test_correct_answers_carry_no_mistake() -> None:
    feedback = check({**REPLY, "verdict": "correct"})
    assert feedback is not None
    assert feedback.error_type is None
    assert feedback.unclassified is False
    assert feedback.mistake_location is None


def test_fragment_ids_are_removed_from_the_explanation() -> None:
    feedback = check(
        {
            **REPLY,
            "explanation": "Según F1, el 2 multiplica a cada término (F2). "
            "Como dice el fragmento F1, quedaría 2x - 6; ver F1 y F2.",
        }
    )
    assert feedback is not None
    assert feedback.explanation == (
        "Según el material, el 2 multiplica a cada término. "
        "Como dice el material, quedaría 2x - 6."
    )
