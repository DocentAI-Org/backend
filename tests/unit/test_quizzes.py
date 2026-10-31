"""Draft validation and the adaptive rule (spec 006 FR-003, FR-006)."""

from app.services.quiz_questions import validate_drafts
from app.services.quizzes import Adaptation, adapt

DRAFT = {
    "statement": "¿Qué queda al quitar el paréntesis en 2(x - 3)? (F1)",
    "options": ["2x - 3", "2x - 6", " 2x + 6 ", "x - 6"],
    "correct": "B",
    "explanation": "El 2 multiplica a cada término, ver F1.",
    "difficulty": 2,
    "cited": ["F1", "F2"],
}


def correct_text(question) -> str:
    return question.options[question.correct_option]


def test_a_grounded_draft_is_accepted_and_cleaned() -> None:
    [question] = validate_drafts({"questions": [DRAFT]}, fragment_count=2, limit=5)
    assert correct_text(question) == "2x - 6"
    assert sorted(question.options) == ["2x + 6", "2x - 3", "2x - 6", "x - 6"]
    assert question.cited_indexes == [0, 1]
    assert "F1" not in question.statement and "F1" not in question.explanation
    assert question.difficulty == 2


def test_the_correct_option_may_be_a_letter_or_an_index() -> None:
    for correct, expected in (("a", "2x - 3"), ("D", "x - 6"), (2, "2x + 6")):
        [question] = validate_drafts(
            {"questions": [DRAFT | {"correct": correct}]}, fragment_count=2, limit=5
        )
        assert correct_text(question) == expected
    [question] = validate_drafts(
        {"questions": [DRAFT | {"correct": "C)"}]}, fragment_count=2, limit=5
    )
    assert correct_text(question) == "2x + 6"


def test_letter_prefixes_are_removed_from_options() -> None:
    lettered = ["A) 2x - 3", "B. 2x - 6", "c) 2x + 6", "D: x - 6"]
    [question] = validate_drafts(
        {"questions": [DRAFT | {"options": lettered}]}, fragment_count=2, limit=5
    )
    assert sorted(question.options) == ["2x + 6", "2x - 3", "2x - 6", "x - 6"]
    # Only a letter matching the option's position is a prefix.
    kept = ["b) uno", "dos", "tres", "cuatro"]
    [question] = validate_drafts(
        {"questions": [DRAFT | {"options": kept}]}, fragment_count=2, limit=5
    )
    assert "b) uno" in question.options


def test_the_correct_option_is_spread_over_positions() -> None:
    drafts = [DRAFT | {"statement": f"Pregunta {i}"} for i in range(5)]
    questions = validate_drafts({"questions": drafts}, fragment_count=2, limit=5)
    assert [q.correct_option for q in questions] == [0, 1, 2, 3, 0]
    assert all(correct_text(q) == "2x - 6" for q in questions)
    # Rotation keeps the order of the options.
    assert questions[0].options == ["2x - 6", "2x + 6", "x - 6", "2x - 3"]


def test_unusable_drafts_are_dropped() -> None:
    bad = [
        DRAFT | {"correct": "E"},
        DRAFT | {"correct": True},
        DRAFT | {"options": ["a", "b", "c"]},
        DRAFT | {"options": ["a", "A", "b", "c"]},
        DRAFT | {"options": ["a", "b", "c", 4]},
        DRAFT | {"cited": ["F3"]},
        DRAFT | {"cited": "F1"},
        DRAFT | {"statement": ""},
        DRAFT | {"explanation": None},
        "texto",
    ]
    assert validate_drafts({"questions": bad}, fragment_count=2, limit=5) == []
    assert validate_drafts({"questions": "x"}, fragment_count=2, limit=5) == []
    assert validate_drafts({}, fragment_count=2, limit=5) == []


def test_an_odd_difficulty_becomes_intermediate() -> None:
    for difficulty in (0, 4, "alta", None, 2.5):
        [question] = validate_drafts(
            {"questions": [DRAFT | {"difficulty": difficulty}]},
            fragment_count=2,
            limit=5,
        )
        assert question.difficulty == 2


def test_drafts_are_limited_and_deduplicated() -> None:
    drafts = [DRAFT | {"statement": f"Pregunta {i}"} for i in range(4)] + [DRAFT, DRAFT]
    questions = validate_drafts(
        {"questions": drafts}, fragment_count=2, limit=5, existing={"pregunta 0"}
    )
    assert [q.statement for q in questions] == [
        "Pregunta 1",
        "Pregunta 2",
        "Pregunta 3",
        "¿Qué queda al quitar el paréntesis en 2(x - 3)?",
    ]


def test_the_level_moves_after_a_streak_and_stays_in_range() -> None:
    assert adapt(level=2, streak=1, correct=True, streak_needed=2) == Adaptation(3, 0)
    assert adapt(level=2, streak=0, correct=True, streak_needed=2) == Adaptation(2, 1)
    assert adapt(level=2, streak=-1, correct=False, streak_needed=2) == Adaptation(1, 0)
    # A right answer after wrong ones starts a new streak.
    assert adapt(level=2, streak=-1, correct=True, streak_needed=2) == Adaptation(2, 1)
    # No level above 3 or below 1: the streak keeps counting without a change.
    assert adapt(level=3, streak=1, correct=True, streak_needed=2) == Adaptation(3, 2)
    assert adapt(level=1, streak=-1, correct=False, streak_needed=2) == Adaptation(
        1, -2
    )
