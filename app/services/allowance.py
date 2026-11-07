"""Messages per student: each course's limit per period, and the study's daily ceiling
across courses (§4.3, research R11, specs/019)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import CourseUsage, DailyUsage
from app.schemas.ai_settings import Limits, Period
from app.schemas.chat import Allowance
from app.services.ai_settings import InEffect

# The single period of a whole-course limit.
COURSE_START = date(1970, 1, 1)


def today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.daily_reset_timezone)).date()


def period_start(settings: Settings, period: Period) -> date:
    day = today(settings)
    if period == "week":
        return day - timedelta(days=day.weekday())
    return day if period == "day" else COURSE_START


def resets_at(settings: Settings, period: Period = "day") -> datetime | None:
    if period == "course":
        return None
    days = 1 if period == "day" else 7
    start = period_start(settings, period) + timedelta(days=days)
    return datetime.combine(start, time(0, 0), ZoneInfo(settings.daily_reset_timezone))


@dataclass(frozen=True)
class Reservation:
    student_id: uuid.UUID
    course_id: uuid.UUID
    day: date | None = None
    period: Period | None = None
    period_start: date | None = None


@dataclass(frozen=True)
class Blocked:
    scope: str
    period: Period


def _take_course(
    session: Session, settings: Settings, limits: Limits, student_id, course_id
) -> date | None:
    start = period_start(settings, limits.period)
    statement = (
        insert(CourseUsage)
        .values(
            student_id=student_id,
            course_id=course_id,
            period=limits.period,
            period_start=start,
            used=1,
        )
        .on_conflict_do_update(
            index_elements=[
                CourseUsage.student_id,
                CourseUsage.course_id,
                CourseUsage.period,
                CourseUsage.period_start,
            ],
            set_={"used": CourseUsage.used + 1},
            where=(CourseUsage.used < limits.messages)
            if limits.messages is not None
            else None,
        )
        .returning(CourseUsage.used)
    )
    return start if session.execute(statement).scalar_one_or_none() else None


def _take_day(
    session: Session, settings: Settings, ceiling: int | None, student_id
) -> date | None:
    day = today(settings)
    statement = (
        insert(DailyUsage)
        .values(student_id=student_id, usage_date=day, used=1)
        .on_conflict_do_update(
            index_elements=[DailyUsage.student_id, DailyUsage.usage_date],
            set_={"used": DailyUsage.used + 1},
            where=(DailyUsage.used < ceiling) if ceiling is not None else None,
        )
        .returning(DailyUsage.used)
    )
    return day if session.execute(statement).scalar_one_or_none() else None


def reserve(
    session: Session,
    settings: Settings,
    ai: InEffect,
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    task: str,
) -> Reservation | Blocked:
    """Atomically takes one message from the course (when it counts the task) and from
    the daily ceiling, which counts every message."""
    limits = ai.limits
    start = None
    if task in limits.counted_tasks:
        start = _take_course(session, settings, limits, student_id, course_id)
        if start is None:
            return Blocked("course", limits.period)
    period = limits.period if start else None
    day = _take_day(session, settings, ai.ceiling.messages, student_id)
    if day is None:
        release(session, Reservation(student_id, course_id, None, period, start))
        return Blocked("daily", "day")
    return Reservation(student_id, course_id, day, period, start)


def release(session: Session, reservation: Reservation) -> None:
    if reservation.day is not None:
        session.execute(
            update(DailyUsage)
            .where(
                DailyUsage.student_id == reservation.student_id,
                DailyUsage.usage_date == reservation.day,
                DailyUsage.used > 0,
            )
            .values(used=DailyUsage.used - 1)
        )
    if reservation.period_start is not None:
        session.execute(
            update(CourseUsage)
            .where(
                CourseUsage.student_id == reservation.student_id,
                CourseUsage.course_id == reservation.course_id,
                CourseUsage.period == reservation.period,
                CourseUsage.period_start == reservation.period_start,
                CourseUsage.used > 0,
            )
            .values(used=CourseUsage.used - 1)
        )


def read_daily(
    session: Session, settings: Settings, ceiling: int | None, student_id: uuid.UUID
) -> Allowance:
    """The daily ceiling across courses."""
    used = (
        session.scalar(
            select(DailyUsage.used).where(
                DailyUsage.student_id == student_id,
                DailyUsage.usage_date == today(settings),
            )
        )
        or 0
    )
    return Allowance(
        scope="daily",
        limit=ceiling,
        used=used,
        remaining=max(ceiling - used, 0) if ceiling is not None else None,
        period="day",
        resets_at=resets_at(settings),
    )


def read(
    session: Session,
    settings: Settings,
    ai: InEffect,
    student_id: uuid.UUID,
    course_id: uuid.UUID,
    task: str = "tutor",
) -> Allowance:
    """The course's allowance for the task, or the daily ceiling when that is tighter or
    the course does not count the task."""
    limits = ai.limits
    daily = read_daily(session, settings, ai.ceiling.messages, student_id)
    if task not in limits.counted_tasks:
        return daily
    used = (
        session.scalar(
            select(CourseUsage.used).where(
                CourseUsage.student_id == student_id,
                CourseUsage.course_id == course_id,
                CourseUsage.period == limits.period,
                CourseUsage.period_start == period_start(settings, limits.period),
            )
        )
        or 0
    )
    course = Allowance(
        scope="course",
        limit=limits.messages,
        used=used,
        remaining=max(limits.messages - used, 0)
        if limits.messages is not None
        else None,
        period=limits.period,
        resets_at=resets_at(settings, limits.period),
    )
    if daily.remaining is not None and (
        course.remaining is None or daily.remaining < course.remaining
    ):
        return daily
    return course
