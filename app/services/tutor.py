"""Grounded tutor replies (S1, S2, S3; constitution I and V; research R4-R6)."""

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Route, Settings
from app.core.errors import ApiError, not_found
from app.llm.client import LLMClient, LLMError
from app.llm.prompts import load_labels, load_prompt
from app.models import (
    Citation,
    Conversation,
    Enrolment,
    Message,
    TutorSettings,
)
from app.schemas import chat as schemas
from app.services import adaptation, ai_settings, allowance, consent, interactions
from app.services.ai_settings import InEffect
from app.services.retrieval import Hit, retrieve

logger = logging.getLogger(__name__)
REPLY_KINDS = {"answer", "hint"}
HISTORY_CHARS = 1000


# --- Views shared with the teacher review --------------------------------------


def citation_view(citation: Citation) -> schemas.Citation:
    fragment = citation.fragment
    available = (
        fragment is not None
        and not fragment.excluded
        and fragment.document.validation_status == "validated"
    )
    return schemas.Citation(
        fragment_id=citation.fragment_id,
        document_name=citation.document_name,
        location_label=citation.location_label,
        passage=fragment.text if available and fragment else None,
        available=available,
    )


def message_view(message: Message) -> schemas.StudentMessage:
    flag = message.flag
    return schemas.StudentMessage(
        id=message.id,
        author=message.author,  # type: ignore[arg-type]
        kind=message.kind,  # type: ignore[arg-type]
        status=message.status,  # type: ignore[arg-type]
        text=message.text,
        hint_number=message.hint_number,
        request_solution=message.request_solution,
        counts_toward_limit=message.counts_toward_limit,
        created_at=message.created_at,
        citations=[citation_view(c) for c in message.citations],
        correction=schemas.Correction(text=flag.correction, reviewed_at=flag.updated_at)
        if flag
        else None,
        adaptation=schemas.Adaptation(**message.adaptation)
        if message.adaptation
        else None,
    )


# --- Grounding --------------------------------------------------------------------


@dataclass(frozen=True)
class GroundedReply:
    kind: str
    text: str
    cited_indexes: list[int] = field(default_factory=list)
    is_problem: bool = False


_FRAGMENT_REF = re.compile(r"F([0-9]{1,3})", re.IGNORECASE)


def cited_fragment_indexes(cited: list, fragment_count: int) -> list[int]:
    """Indexes of the given fragments ("F1", "F2"...) that the model cites."""
    indexes: list[int] = []
    for ref in cited:
        match = _FRAGMENT_REF.fullmatch(ref) if isinstance(ref, str) else None
        if match is None:
            continue
        index = int(match.group(1)) - 1
        if 0 <= index < fragment_count and index not in indexes:
            indexes.append(index)
    return indexes


def ground_reply(data: dict, fragment_count: int) -> GroundedReply:
    """Accepts a model reply only if it cites fragments it was actually given.

    Anything unexpected in the model output becomes `no_source`, never an error.
    """
    kind = data.get("kind")
    text = data.get("text")
    cited = data.get("cited")
    if not isinstance(kind, str) or kind not in REPLY_KINDS:
        return GroundedReply("no_source", "")
    if not isinstance(text, str) or not text.strip() or not isinstance(cited, list):
        return GroundedReply("no_source", "")
    indexes = cited_fragment_indexes(cited, fragment_count)
    if not indexes:
        return GroundedReply("no_source", "")
    return GroundedReply(
        kind, text.strip(), indexes, is_problem=data.get("is_problem") is True
    )


def solution_allowed(tutor_settings: TutorSettings, request_solution: bool) -> bool:
    policy = tutor_settings.solution_policy
    return policy == "direct" or (policy == "hints_first" and request_solution)


def no_source_text(settings: Settings) -> str:
    return load_labels("messages", settings.tutor_language)["no_source"]


def build_system_prompt(
    settings: Settings,
    tutor_settings: TutorSettings,
    request_solution: bool,
    note: str | None = None,
) -> str:
    """The adaptation note (spec 013) is one more rule, before the reply format."""
    labels = load_labels("policies", settings.tutor_language)
    policy = labels[f"policy.{tutor_settings.solution_policy}"]
    if request_solution and tutor_settings.solution_policy != "hints_only":
        policy = f"{policy} {labels['policy.solution_requested']}"
    return load_prompt("tutor_system", settings.tutor_language).format(
        level=labels[f"level.{tutor_settings.level}"],
        tone=labels[f"tone.{tutor_settings.tone}"],
        policy=policy,
        adaptation=f"\n7. {note}" if note else "",
    )


def build_messages(
    history: list[Message], hits: list[Hit], question: str
) -> list[dict[str, str]]:
    """Only course material and message texts: no names, emails or ids."""
    turns = [
        {
            "role": "user" if m.author == "student" else "assistant",
            "content": m.text[:HISTORY_CHARS],
        }
        for m in history
    ]
    turns.append(
        {
            "role": "user",
            "content": f"{material_block(hits)}\n\n<pregunta>\n{question}\n</pregunta>",
        }
    )
    return turns


def material_block(hits: list[Hit], topic_refs: list[str | None] | None = None) -> str:
    """The retrieved fragments, numbered F1, F2... so the model can cite them, with
    the topic of each one when given (spec 009)."""
    refs = topic_refs or [None] * len(hits)
    material = "\n\n".join(
        f'<fragmento id="F{i}" '
        f'fuente="{hit.document_name}, {hit.fragment.location_label}"'
        + (f' tema="{ref}"' if ref else "")
        + f">\n{hit.fragment.text}\n</fragmento>"
        for i, (hit, ref) in enumerate(zip(hits, refs, strict=True), start=1)
    )
    return f"<material>\n{material}\n</material>"


# --- Conversation flow ------------------------------------------------------------


def get_conversation(
    session: Session, enrolment: Enrolment, conversation_id: uuid.UUID
) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.course_id != enrolment.course_id
        or conversation.student_id != enrolment.student_id
    ):
        raise not_found("Conversation")
    return conversation


def conversation_messages(
    session: Session, conversation_id: uuid.UUID
) -> list[Message]:
    return list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        ).all()
    )


def _history(
    session: Session, conversation: Conversation, exclude: uuid.UUID, limit: int
) -> list[Message]:
    rows = session.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.status == "sent",
            Message.id != exclude,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def _next_hint_number(history: list[Message]) -> int:
    count = 0
    for message in reversed(history):
        if message.author == "student":
            continue
        if message.kind != "hint":
            break
        count += 1
    return count + 1


def _retrieve_for(
    session: Session,
    llm: LLMClient,
    ai: InEffect,
    course_id: uuid.UUID,
    history: list[Message],
    text: str,
) -> list[Hit]:
    """The question alone decides; inside a guided exercise (the last reply was a
    hint), a follow-up such as "no lo entiendo" also searches with the previous
    question. Joining them always would let any new question ride on the last one.
    """
    hits = retrieve(
        session,
        llm,
        course_id,
        text,
        ai.retrieval.top_k,
        ai.retrieval.min_similarity,
    )
    last = history[-1] if history else None
    if hits or last is None or last.author != "tutor" or last.kind != "hint":
        return hits
    previous = next((m.text for m in reversed(history) if m.author == "student"), "")
    return retrieve(
        session,
        llm,
        course_id,
        f"{previous}\n{text}",
        ai.retrieval.top_k,
        ai.retrieval.min_similarity,
    )


def ensure_can_message(
    session: Session, settings: Settings, enrolment: Enrolment, request_solution: bool
) -> TutorSettings:
    # Before anything is reserved or sent to the model (specs/002 FR-004).
    consent.require(session, settings, enrolment.student_id)
    if enrolment.disclosure_acknowledged_at is None:
        raise ApiError(
            409,
            "disclosure_not_acknowledged",
            "The student must acknowledge the AI tutor disclosure first.",
        )
    tutor_settings = session.get(TutorSettings, enrolment.course_id)
    assert tutor_settings is not None
    if request_solution and tutor_settings.solution_policy == "hints_only":
        raise ApiError(
            409,
            "solution_not_allowed",
            "The teacher only allows hints in this course.",
        )
    return tutor_settings


def reserve_or_raise(
    session: Session, settings: Settings, ai: InEffect, enrolment: Enrolment, task: str
) -> allowance.Reservation:
    taken = allowance.reserve(
        session, settings, ai, enrolment.student_id, enrolment.course_id, task
    )
    if isinstance(taken, allowance.Reservation):
        return taken
    resets_at = allowance.resets_at(settings, taken.period)
    details = {"resets_at": resets_at.isoformat() if resets_at else None}
    if taken.scope == "daily":
        raise ApiError(
            429,
            "daily_limit_reached",
            "The daily message limit has been reached.",
            details,
        )
    raise ApiError(
        429,
        "course_limit_reached",
        "The course's message limit has been reached.",
        {**details, "period": taken.period},
    )


def allowance_view(
    session: Session, settings: Settings, ai: InEffect, enrolment: Enrolment
) -> schemas.Allowance:
    return allowance.read(
        session, settings, ai, enrolment.student_id, enrolment.course_id
    )


def send_message(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    enrolment: Enrolment,
    conversation: Conversation,
    text: str,
    request_solution: bool,
    retry_of: Message | None = None,
) -> schemas.TutorExchange:
    tutor_settings = ensure_can_message(session, settings, enrolment, request_solution)
    ai = ai_settings.in_effect(session, settings, enrolment.course_id)
    reservation = reserve_or_raise(session, settings, ai, enrolment, "tutor")

    if retry_of is None:
        student_message = Message(
            conversation_id=conversation.id,
            author="student",
            kind="question",
            text=text,
            request_solution=request_solution,
        )
        session.add(student_message)
    else:
        student_message = retry_of
    student_message.status = "sent"
    student_message.counts_toward_limit = reservation.period_start is not None
    session.flush()
    # The reservation and the question are kept even if the model call is slow.
    session.commit()

    started = time.perf_counter()
    try:
        return _reply(
            session,
            llm,
            settings,
            ai,
            enrolment,
            conversation,
            tutor_settings,
            student_message,
            request_solution,
            started,
        )
    except Exception as exc:
        # Whatever went wrong after the commit, the student is not charged and
        # can retry (FR-061).
        if not isinstance(exc, LLMError):
            logger.exception("Tutor reply failed for message %s", student_message.id)
        _fail(session, settings, enrolment, student_message, reservation, started)
        raise ApiError(
            503,
            "tutor_unavailable",
            "The tutor could not answer. The message did not count.",
            {"message_id": str(student_message.id)},
        ) from None


@dataclass
class _ModelReply:
    reply: GroundedReply
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def _ask_model(
    llm: LLMClient,
    settings: Settings,
    route: Route,
    tutor_settings: TutorSettings,
    request_solution: bool,
    history: list[Message],
    hits: list[Hit],
    text: str,
    note: str | None = None,
) -> _ModelReply:
    system = build_system_prompt(settings, tutor_settings, request_solution, note)
    messages = build_messages(history, hits, text)
    result = llm.chat_json(system, messages, task="tutor", route=route)
    outcome = _ModelReply(
        ground_reply(result.data, len(hits)),
        result.model,
        result.input_tokens,
        result.output_tokens,
    )
    reply = outcome.reply
    if (
        reply.kind != "answer"
        or not reply.is_problem
        or solution_allowed(tutor_settings, request_solution)
    ):
        return outcome

    # The policy forbids a full solution here (FR-054): ask once more, then fall
    # back to a generic hint on the same cited material.
    labels = load_labels("messages", settings.tutor_language)
    retry = llm.chat_json(
        f"{system}\n\n{labels['hint_reminder']}", messages, task="tutor", route=route
    )
    outcome.input_tokens += retry.input_tokens
    outcome.output_tokens += retry.output_tokens
    second = ground_reply(retry.data, len(hits))
    if second.kind == "hint":
        outcome.reply = second
    else:
        outcome.reply = GroundedReply(
            "hint", labels["hint_fallback"], reply.cited_indexes, is_problem=True
        )
    return outcome


def _reply(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    ai: InEffect,
    enrolment: Enrolment,
    conversation: Conversation,
    tutor_settings: TutorSettings,
    student_message: Message,
    request_solution: bool,
    started: float,
) -> schemas.TutorExchange:
    history = _history(
        session, conversation, student_message.id, ai.retrieval.history_messages
    )
    hits = _retrieve_for(
        session, llm, ai, enrolment.course_id, history, student_message.text
    )
    focus = adaptation.focus(
        session, settings, enrolment.course_id, enrolment.student_id
    )
    answered = (
        _ask_model(
            llm,
            settings,
            ai.route("tutor"),
            tutor_settings,
            request_solution,
            history,
            hits,
            student_message.text,
            adaptation.prompt_note(session, settings, focus),
        )
        if hits
        else _ModelReply(GroundedReply("no_source", ""))
    )
    reply = answered.reply
    latency_ms = int((time.perf_counter() - started) * 1000)
    cited_hits = [hits[i] for i in reply.cited_indexes]
    tutor_message = Message(
        conversation_id=conversation.id,
        author="tutor",
        kind=reply.kind,
        text=reply.text or no_source_text(settings),
        hint_number=_next_hint_number(history) if reply.kind == "hint" else None,
        adaptation=focus.model_dump()
        if focus and reply.kind in ("answer", "hint")
        else None,
    )
    session.add(tutor_message)
    session.flush()
    session.add_all(
        Citation(
            message_id=tutor_message.id,
            fragment_id=hit.fragment.id,
            document_name=hit.document_name,
            location_label=hit.fragment.location_label,
            position=position,
        )
        for position, hit in enumerate(cited_hits, start=1)
    )
    conversation.last_message_at = datetime.now(UTC)
    interactions.record(
        session,
        settings,
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        kind="chat",
        question=student_message.text,
        fragment_ids=[hit.fragment.id for hit in hits],
        outcome=reply.kind,
        answer=tutor_message.text,
        model=answered.model,
        input_tokens=answered.input_tokens,
        output_tokens=answered.output_tokens,
        latency_ms=latency_ms,
    )
    session.flush()
    session.refresh(tutor_message)
    return schemas.TutorExchange(
        student_message=message_view(student_message),
        tutor_message=message_view(tutor_message),
        allowance=allowance_view(session, settings, ai, enrolment),
    )


def _fail(
    session: Session,
    settings: Settings,
    enrolment: Enrolment,
    student_message: Message,
    reservation: allowance.Reservation,
    started: float,
) -> None:
    session.rollback()
    allowance.release(session, reservation)
    student_message.status = "failed"
    student_message.counts_toward_limit = False
    interactions.record(
        session,
        settings,
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        kind="chat",
        question=student_message.text,
        fragment_ids=[],
        outcome="error",
        latency_ms=int((time.perf_counter() - started) * 1000),
        error_code="tutor_unavailable",
    )
    session.commit()


def list_conversations(
    session: Session, enrolment: Enrolment, limit: int, offset: int
) -> tuple[list[schemas.StudentConversationSummary], int]:
    query = select(Conversation).where(
        Conversation.course_id == enrolment.course_id,
        Conversation.student_id == enrolment.student_id,
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Conversation.last_message_at.desc(), Conversation.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = []
    for conversation in rows:
        first = session.scalar(
            select(Message.text)
            .where(
                Message.conversation_id == conversation.id,
                Message.author == "student",
            )
            .order_by(Message.created_at)
            .limit(1)
        )
        items.append(
            schemas.StudentConversationSummary(
                id=conversation.id,
                started_at=conversation.started_at,
                last_message_at=conversation.last_message_at,
                preview=first[:120] if first else None,
            )
        )
    return items, total


def conversation_view(
    session: Session, conversation: Conversation
) -> schemas.Conversation:
    return schemas.Conversation(
        id=conversation.id,
        started_at=conversation.started_at,
        last_message_at=conversation.last_message_at,
        messages=[
            message_view(m) for m in conversation_messages(session, conversation.id)
        ],
    )
