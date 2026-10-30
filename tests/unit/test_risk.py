"""Evaluation of the provisional at-risk criteria (spec 004, risk-criteria.md)."""

from datetime import UTC, datetime, timedelta

from app.services.risk import Criterion, StudentFacts, evaluate

NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)
CRITERIA = [
    Criterion("inactive", True, {"days": 7}),
    Criterion("error_rate", True, {"window_days": 14, "min_exercises": 5, "rate": 0.6}),
]


def facts(
    joined: float = 30,
    last: float | None = 1,
    assessed: int = 0,
    mistakes: int = 0,
) -> StudentFacts:
    return StudentFacts(
        joined_at=NOW - timedelta(days=joined),
        last_activity_at=None if last is None else NOW - timedelta(days=last),
        assessed=assessed,
        mistakes=mistakes,
    )


def codes(student: StudentFacts, criteria=CRITERIA) -> list[str]:
    return [r.criterion for r in evaluate(criteria, student, NOW)]


def test_inactivity_starts_at_the_threshold() -> None:
    assert codes(facts(last=6.9)) == []
    assert codes(facts(last=7)) == ["inactive"]


def test_inactivity_without_activity_counts_from_joining() -> None:
    assert codes(facts(joined=6, last=None)) == []
    [reason] = evaluate(CRITERIA, facts(joined=8, last=None), NOW)
    assert (reason.days_inactive, reason.never_active) == (8, True)
    assert reason.since == NOW - timedelta(days=8)


def test_error_rate_needs_enough_exercises_and_the_rate() -> None:
    assert codes(facts(assessed=4, mistakes=4)) == []
    assert codes(facts(assessed=10, mistakes=5)) == []
    assert codes(facts(assessed=10, mistakes=6)) == ["error_rate"]
    assert codes(facts(assessed=5, mistakes=3)) == ["error_rate"]


def test_disabled_criteria_are_never_applied() -> None:
    disabled = [Criterion(c.code, False, c.thresholds) for c in CRITERIA]
    assert codes(facts(last=30, assessed=10, mistakes=10), disabled) == []


def test_reasons_follow_the_criteria_order_and_carry_the_applied_thresholds() -> None:
    stricter = [
        Criterion("inactive", True, {"days": 3}),
        Criterion(
            "error_rate", True, {"window_days": 7, "min_exercises": 2, "rate": 0.5}
        ),
    ]
    inactive, rate = evaluate(stricter, facts(last=4, assessed=2, mistakes=1), NOW)
    assert (inactive.criterion, inactive.threshold_days) == ("inactive", 3)
    assert (rate.window_days, rate.min_exercises, rate.threshold_rate) == (7, 2, 0.5)
