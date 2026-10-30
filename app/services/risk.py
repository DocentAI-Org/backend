"""At-risk criteria (specs/004, risk-criteria.md): computed per request, not stored."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, RiskCriterion
from app.schemas.dashboard import ErrorRateReason, InactiveReason, RiskReason


@dataclass(frozen=True)
class Criterion:
    code: str
    enabled: bool
    thresholds: dict


@dataclass(frozen=True)
class StudentFacts:
    joined_at: datetime
    last_activity_at: datetime | None
    # Within the error_rate window: assessed exercises and those with a mistake.
    assessed: int
    mistakes: int


def all_criteria(session: Session) -> list[RiskCriterion]:
    return list(session.scalars(select(RiskCriterion).order_by(RiskCriterion.position)))


def criteria_for(session: Session, course: Course) -> tuple[list[Criterion], bool]:
    """The criteria applied to a course and whether they are provisional.

    Global for now; per-course overrides set by the teacher go here later (spec 004).
    """
    rows = all_criteria(session)
    criteria = [Criterion(r.code, r.enabled, r.thresholds) for r in rows]
    return criteria, any(r.provisional for r in rows)


def enabled(criteria: list[Criterion], code: str) -> Criterion | None:
    return next((c for c in criteria if c.code == code and c.enabled), None)


def evaluate(
    criteria: list[Criterion], facts: StudentFacts, now: datetime
) -> list[RiskReason]:
    reasons: list[RiskReason] = []
    for criterion in criteria:
        if not criterion.enabled:
            continue
        t = criterion.thresholds
        if criterion.code == "inactive":
            since = facts.last_activity_at or facts.joined_at
            days = (now - since).days
            if days >= t["days"]:
                reasons.append(
                    InactiveReason(
                        criterion="inactive",
                        days_inactive=days,
                        threshold_days=t["days"],
                        since=since,
                        never_active=facts.last_activity_at is None,
                    )
                )
        elif criterion.code == "error_rate":
            if (
                facts.assessed > 0
                and facts.assessed >= t["min_exercises"]
                and facts.mistakes / facts.assessed >= t["rate"]
            ):
                reasons.append(
                    ErrorRateReason(
                        criterion="error_rate",
                        mistakes=facts.mistakes,
                        assessed=facts.assessed,
                        window_days=t["window_days"],
                        min_exercises=t["min_exercises"],
                        threshold_rate=t["rate"],
                    )
                )
    return reasons
