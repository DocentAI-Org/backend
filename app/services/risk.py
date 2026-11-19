"""At-risk criteria (specs/004, risk-criteria.md): computed per request, not stored."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Course
from app.schemas.dashboard import ErrorRateReason, InactiveReason, RiskReason
from app.schemas.pedagogy import Criteria
from app.services import pedagogy


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


def _from(criteria: Criteria) -> list[Criterion]:
    inactive, error_rate = criteria.inactive, criteria.error_rate
    return [
        Criterion("inactive", inactive.enabled, {"days": inactive.days}),
        Criterion(
            "error_rate",
            error_rate.enabled,
            {
                "window_days": error_rate.window_days,
                "min_exercises": error_rate.min_exercises,
                "rate": error_rate.rate,
            },
        ),
    ]


def study_criteria(session: Session) -> tuple[list[Criterion], bool]:
    """The study's defaults (specs/015)."""
    defaults = pedagogy.study(session)
    return _from(defaults.criteria), defaults.provisional


def criteria_for(session: Session, course: Course) -> tuple[list[Criterion], bool]:
    """The criteria applied to a course (its own or the study's, specs/015) and whether
    they are provisional."""
    current = pedagogy.in_effect(session, course.id)
    return _from(current.criteria), current.provisional


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
        elif criterion.code == "error_rate" and (
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
