"""Interaction log for every model call (P2, AGENTS.md V and VI, research R12)."""

import hashlib
import hmac
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.types import InteractionKind, Outcome
from app.models import InteractionLog


def student_ref(settings: Settings, student_id: uuid.UUID | str) -> str:
    """Keyed hash: logs never store the account id, but erasure can find them."""
    return hmac.new(
        settings.log_pseudonym_secret.encode(),
        str(student_id).encode(),
        hashlib.sha256,
    ).hexdigest()


# Anthropic list prices (USD per million tokens, input and output), 2026-10;
# LLM_PRICES overrides them and adds other models (specs/014).
KNOWN_PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


def estimate_cost(
    settings: Settings, input_tokens: int, output_tokens: int, model: str | None = None
) -> Decimal:
    price_in, price_out = {**KNOWN_PRICES, **settings.llm_prices}.get(
        model or "",
        (settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok),
    )
    return (
        Decimal(str(price_in)) * input_tokens + Decimal(str(price_out)) * output_tokens
    ) / Decimal(1_000_000)


def record(
    session: Session,
    settings: Settings,
    *,
    course_id: uuid.UUID,
    student_id: uuid.UUID | None,
    kind: InteractionKind,
    question: str,
    fragment_ids: list[uuid.UUID],
    outcome: Outcome,
    answer: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    error_code: str | None = None,
) -> InteractionLog:
    log = InteractionLog(
        course_id=course_id,
        student_ref=student_ref(settings, student_id) if student_id else None,
        kind=kind,
        question=question,
        retrieved_fragment_ids=fragment_ids,
        answer=answer,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        estimated_cost_usd=estimate_cost(settings, input_tokens, output_tokens, model),
        outcome=outcome,
        error_code=error_code,
    )
    session.add(log)
    return log
