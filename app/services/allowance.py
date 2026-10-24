"""Per-student daily message allowance shared across courses (§4.3, research R11)."""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import DailyUsage
from app.schemas.chat import Allowance


def today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.daily_reset_timezone)).date()


def resets_at(settings: Settings) -> datetime:
    zone = ZoneInfo(settings.daily_reset_timezone)
    return datetime.combine(today(settings) + timedelta(days=1), time(0, 0), zone)


def reserve(session: Session, settings: Settings, student_id: uuid.UUID) -> date | None:
    """Atomically takes one message; returns the usage day, or None at the limit."""
    day = today(settings)
    statement = (
        insert(DailyUsage)
        .values(student_id=student_id, usage_date=day, used=1)
        .on_conflict_do_update(
            index_elements=[DailyUsage.student_id, DailyUsage.usage_date],
            set_={"used": DailyUsage.used + 1},
            where=DailyUsage.used < settings.daily_message_limit,
        )
        .returning(DailyUsage.used)
    )
    used = session.execute(statement).scalar_one_or_none()
    return day if used is not None else None


def release(session: Session, student_id: uuid.UUID, day: date) -> None:
    session.execute(
        update(DailyUsage)
        .where(
            DailyUsage.student_id == student_id,
            DailyUsage.usage_date == day,
            DailyUsage.used > 0,
        )
        .values(used=DailyUsage.used - 1)
    )


def read(session: Session, settings: Settings, student_id: uuid.UUID) -> Allowance:
    used = (
        session.scalar(
            select(DailyUsage.used).where(
                DailyUsage.student_id == student_id,
                DailyUsage.usage_date == today(settings),
            )
        )
        or 0
    )
    limit = settings.daily_message_limit
    return Allowance(
        limit=limit,
        used=used,
        remaining=max(limit - used, 0),
        resets_at=resets_at(settings),
    )
