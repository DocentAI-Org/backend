"""Score, level and weekly history of a topic (spec 007, provisional criteria)."""

from datetime import UTC, date, datetime, timedelta

from app.services.progress import Criteria, Item, history_of, level_of, score_of

CRITERIA = Criteria(window=4, min_items=3, progressing=0.5, mastered=0.8)
START = datetime(2026, 10, 5, 10, tzinfo=UTC)  # a Monday


def items(*values: float, every_days: int = 1) -> list[Item]:
    return [
        Item(at=START + timedelta(days=i * every_days), value=v)
        for i, v in enumerate(values)
    ]


def test_the_score_is_the_mean_of_the_latest_items() -> None:
    assert score_of(items(1, 1, 0.5, 0), CRITERIA) == 0.625
    # Only the last `window` items count.
    assert score_of(items(0, 0, 1, 1, 1, 1), CRITERIA) == 1.0


def test_too_few_items_have_no_score() -> None:
    assert score_of(items(1, 1), CRITERIA) is None
    assert score_of([], CRITERIA) is None


def test_levels_follow_the_thresholds() -> None:
    assert level_of(0, None, CRITERIA) == "not_started"
    assert level_of(2, None, CRITERIA) == "insufficient"
    assert level_of(3, 0.49, CRITERIA) == "starting"
    assert level_of(3, 0.5, CRITERIA) == "progressing"
    assert level_of(3, 0.79, CRITERIA) == "progressing"
    assert level_of(3, 0.8, CRITERIA) == "mastered"


def test_history_scores_each_week_with_the_items_up_to_its_end() -> None:
    weeks = [date(2026, 10, 5) + timedelta(weeks=i) for i in range(4)]
    # Days 0 and 4 (week 1), 8 and 12 (week 2), 16 (week 3), nothing in week 4.
    log = items(0, 0, 1, 1, 1, every_days=4)

    assert history_of(log, weeks, CRITERIA) == [None, 0.5, 0.75, 0.75]
