"""Grounded tutor replies (S1, S2, S3; constitution I and V; research R4-R6)."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
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
from app.services import allowance, interactions
from app.services.retrieval import Hit, retrieve

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
    )


# --- Grounding --------------------------------------------------------------------


@dataclass(frozen=True)
class GroundedReply:
    kind: str
    text: str
    cited_indexes: list[int] = field(default_factory=list)


def ground_reply(data: dict, fragment_count: int) -> GroundedReply:
    """Accepts a model reply only if it cites fragments it was actually given."""
    kind = data.get("kind")
    text = data.get("text")
    cited = data.get("cited")
    if kind not in REPLY_KINDS or not isinstance(text, str) or not text.strip():
        return GroundedReply("no_source", "")
    if not isinstance(cited, list):
        return GroundedReply("no_source", "")
    indexes: list[int] = []
    for ref in cited:
        if isinstance(ref, str) and ref.upper().startswith("F") and ref[1:].isdigit():
            index = int(ref[1:]) - 1
            if 0 <= index < fragment_count and index not in indexes:
                indexes.append(index)
    if not indexes:
        return GroundedReply("no_source", "")
    return GroundedReply(kind, text.strip(), indexes)


def no_source_text(settings: Settings) -> str:
    return load_labels("messages", settings.tutor_language)["no_source"]


def build_system_prompt(
    settings: Settings, tutor_settings: TutorSettings, request_solution: bool
) -> str:
    labels = load_labels("policies", settings.tutor_language)
    policy = labels[f"policy.{tutor_settings.solution_policy}"]
    if request_solution and tutor_settings.solution_policy != "hints_only":
        policy = f"{policy} {labels['policy.solution_requested']}"
    return load_prompt("tutor_system", settings.tutor_language).format(
        level=labels[f"level.{tutor_settings.level}"],
        tone=labels[f"tone.{tutor_settings.tone}"],
        policy=policy,
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
    material = "\n\n".join(
        f'<fragmento id="F{i}" '
        f'fuente="{hit.document_name}, {hit.fragment.location_label}">'
        f"\n{hit.fragment.text}\n</fragmento>"
        for i, hit in enumerate(hits, start=1)
    )
    turns.append(
        {
            "role": "user",
            "content": f"<material>\n{material}\n</material>\n\n"
            f"<pregunta>\n{question}\n</pregunta>",
        }
    )
    return turns


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
    settings: Settings,
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
        settings.retrieval_top_k,
        settings.retrieval_min_similarity,
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
        settings.retrieval_top_k,
        settings.retrieval_min_similarity,
    )


def ensure_can_message(
    session: Session, enrolment: Enrolment, request_solution: bool
) -> TutorSettings:
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


def reserve_or_raise(session: Session, settings: Settings, student_id: uuid.UUID):
    day = allowance.reserve(session, settings, student_id)
    if day is None:
        raise ApiError(
            429,
            "daily_limit_reached",
            "The daily message limit has been reached.",
            {"resets_at": allowance.resets_at(settings).isoformat()},
        )
    return day


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
    tutor_settings = ensure_can_message(session, enrolment, request_solution)
    day = reserve_or_raise(session, settings, enrolment.student_id)

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
    student_message.counts_toward_limit = True
    session.flush()
    # The reservation and the question are kept even if the model call is slow.
    session.commit()

    history = _history(
        session, conversation, student_message.id, settings.history_max_messages
    )
    started = time.perf_counter()
    hits: list[Hit] = []
    try:
        hits = _retrieve_for(
            session, llm, settings, enrolment.course_id, history, student_message.text
        )
        if hits:
            result = llm.chat_json(
                build_system_prompt(settings, tutor_settings, request_solution),
                build_messages(history, hits, student_message.text),
            )
        else:
            result = None
    except LLMError:
        _fail(session, settings, enrolment, student_message, day, hits, started)
        raise ApiError(
            503,
            "tutor_unavailable",
            "The tutor could not answer. The message did not count.",
            {"message_id": str(student_message.id)},
        ) from None

    latency_ms = int((time.perf_counter() - started) * 1000)
    reply = (
        ground_reply(result.data, len(hits))
        if result
        else GroundedReply("no_source", "")
    )
    cited_hits = [hits[i] for i in reply.cited_indexes]
    tutor_message = Message(
        conversation_id=conversation.id,
        author="tutor",
        kind=reply.kind,
        text=reply.text or no_source_text(settings),
        hint_number=_next_hint_number(history) if reply.kind == "hint" else None,
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
        model=result.model if result else None,
        input_tokens=result.input_tokens if result else 0,
        output_tokens=result.output_tokens if result else 0,
        latency_ms=latency_ms,
    )
    session.flush()
    session.refresh(tutor_message)
    return schemas.TutorExchange(
        student_message=message_view(student_message),
        tutor_message=message_view(tutor_message),
        allowance=allowance.read(session, settings, enrolment.student_id),
    )


def _fail(
    session: Session,
    settings: Settings,
    enrolment: Enrolment,
    student_message: Message,
    day,
    hits: list[Hit],
    started: float,
) -> None:
    session.rollback()
    allowance.release(session, enrolment.student_id, day)
    student_message.status = "failed"
    student_message.counts_toward_limit = False
    interactions.record(
        session,
        settings,
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        kind="chat",
        question=student_message.text,
        fragment_ids=[hit.fragment.id for hit in hits],
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
