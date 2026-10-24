"""Interaction log for every model call (P2, constitution V and VI, research R12)."""

import hashlib
import hmac
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import InteractionLog


def student_ref(settings: Settings, student_id: uuid.UUID | str) -> str:
    """Keyed hash: logs never store the account id, but erasure can find them."""
    return hmac.new(
        settings.log_pseudonym_secret.encode(),
        str(student_id).encode(),
        hashlib.sha256,
    ).hexdigest()


def estimate_cost(settings: Settings, input_tokens: int, output_tokens: int) -> Decimal:
    cost = (
        Decimal(str(settings.llm_price_input_per_mtok)) * input_tokens
        + Decimal(str(settings.llm_price_output_per_mtok)) * output_tokens
    ) / Decimal(1_000_000)
    return cost


def record(
    session: Session,
    settings: Settings,
    *,
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    kind: str,
    question: str,
    fragment_ids: list[uuid.UUID],
    outcome: str,
    answer: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    error_code: str | None = None,
) -> InteractionLog:
    log = InteractionLog(
        course_id=course_id,
        student_ref=student_ref(settings, student_id),
        kind=kind,
        question=question,
        retrieved_fragment_ids=fragment_ids,
        answer=answer,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        estimated_cost_usd=estimate_cost(settings, input_tokens, output_tokens),
        outcome=outcome,
        error_code=error_code,
    )
    session.add(log)
    return log
