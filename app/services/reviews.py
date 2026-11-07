"""Targeted review of a repeated mistake (S5, specs/005): what is going wrong, a worked
example and practice statements, grounded in the course material."""

import logging
import re
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.llm.client import ChatResult, LLMClient, LLMError
from app.llm.prompts import load_labels, load_prompt
from app.models import (
    Citation,
    Enrolment,
    ErrorType,
    ExerciseSubmission,
    MistakeReview,
    TutorSettings,
)
from app.schemas import exercises as schemas
from app.services import ai_settings, allowance, exercises, interactions, tutor
from app.services.ai_settings import InEffect
from app.services.retrieval import Hit, retrieve

logger = logging.getLogger(__name__)

PRACTICE_ITEMS = 2
TEXT_CHARS = 2000


@dataclass
class Review:
    explanation: str
    cited_indexes: list[int]
    practice: list[str]
    worked_example: str | None = None


_EXPRESSION = re.compile(r"[^\n:;¿?.]*=[^\n:;¿?]*")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower().rstrip(".")


def expressions(statement: str) -> set[str]:
    """The equations in the student's statement, without spaces, e.g. "2(x-3)=4x+2"."""
    return {
        compact
        for match in _EXPRESSION.findall(statement)
        if len(compact := _compact(match)) >= 5
    }


def copies(text: str, own: set[str]) -> bool:
    compact = _compact(text)
    return any(expression in compact for expression in own)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:TEXT_CHARS]
    return None


def validate_review(
    data: dict, fragment_count: int, statement: str = ""
) -> Review | None:
    """Accepts the review only if grounded and with something to practise (FR-004).

    A worked example or practice item that copies the student's own equation is dropped:
    the review must not solve the student's exercise (US2 AS4).
    """
    own = expressions(statement)
    explanation = _text(data.get("explanation"))
    cited = data.get("cited")
    practice = data.get("practice")
    if explanation is None or not isinstance(cited, list):
        return None
    indexes = tutor.cited_fragment_indexes(cited, fragment_count)
    statements = (
        [text for item in practice if (text := _text(item)) and not copies(text, own)][
            :PRACTICE_ITEMS
        ]
        if isinstance(practice, list)
        else []
    )
    if not indexes or not statements:
        return None
    example = _text(data.get("worked_example"))
    if example and copies(example, own):
        example = None
    return Review(
        explanation=exercises.without_fragment_refs(explanation),
        cited_indexes=indexes,
        practice=statements,
        worked_example=exercises.without_fragment_refs(example) if example else None,
    )


def build_review_prompt(
    settings: Settings, tutor_settings: TutorSettings, teacher: str | None = None
) -> str:
    labels = load_labels("policies", settings.tutor_language)
    rule = (
        "review.solution_allowed"
        if tutor_settings.solution_policy == "direct"
        else "review.no_solution"
    )
    return load_prompt("mistake_review", settings.tutor_language).format(
        level=labels[f"level.{tutor_settings.level}"],
        tone=labels[f"tone.{tutor_settings.tone}"],
        solution_rule=labels[rule],
        teacher=tutor.teacher_block(settings, teacher),
    )


def build_review_messages(
    hits: list[Hit],
    error_type: ErrorType,
    topic_name: str | None,
    submission: ExerciseSubmission,
) -> list[dict[str, str]]:
    """Only course material, the pattern and the exercise; no personal data."""
    topic = f"\nTema: {topic_name}" if topic_name else ""
    return [
        {
            "role": "user",
            "content": f"{tutor.material_block(hits)}\n\n"
            f"<error>\n{error_type.label_es}: {error_type.description_es}{topic}\n"
            f"</error>\n\n"
            f"<enunciado>\n{submission.problem_statement}\n</enunciado>\n\n"
            f"<respuesta>\n{submission.worked_answer}\n</respuesta>",
        }
    ]


def review_view(review: MistakeReview) -> schemas.MistakeReview:
    return schemas.MistakeReview(
        id=review.id,
        submission_id=review.submission_id,
        error_type=review.error_type,
        topic_name=review.topic_name,
        kind=review.kind,  # type: ignore[arg-type]
        explanation=review.explanation,
        worked_example=review.worked_example,
        practice=list(review.practice),
        citations=[tutor.citation_view(c) for c in review.citations],
        created_at=review.created_at,
    )


def get_review(session: Session, submission_id: uuid.UUID) -> MistakeReview | None:
    return session.scalar(
        select(MistakeReview).where(MistakeReview.submission_id == submission_id)
    )


def read_review(session: Session, submission_id: uuid.UUID) -> schemas.MistakeReview:
    review = get_review(session, submission_id)
    if review is None:
        raise not_found("Review")
    return review_view(review)


def request_review(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    enrolment: Enrolment,
    submission: ExerciseSubmission,
) -> tuple[schemas.MistakeReview, bool]:
    """The review and whether it is new; an existing one costs nothing (US2 AS2)."""
    existing = get_review(session, submission.id)
    if existing is not None:
        return review_view(existing), False
    repeated = exercises.repeated_mistake(session, settings, submission)
    if repeated is None:
        raise ApiError(
            409, "no_repeated_mistake", "This mistake does not repeat a pattern."
        )
    tutor_settings = tutor.ensure_can_message(
        session, settings, enrolment, request_solution=False
    )
    ai = ai_settings.in_effect(session, settings, enrolment.course_id)
    reservation = tutor.reserve_or_raise(session, settings, ai, enrolment, "review")
    session.commit()
    started = time.perf_counter()
    try:
        review = _create(
            session, llm, settings, ai, tutor_settings, submission, repeated, started
        )
    except Exception as exc:
        if not isinstance(exc, LLMError):
            logger.exception("Mistake review failed in course %s", enrolment.course_id)
        session.rollback()
        allowance.release(session, reservation)
        interactions.record(
            session,
            settings,
            course_id=enrolment.course_id,
            student_id=enrolment.student_id,
            kind="review",
            question=submission.problem_statement,
            fragment_ids=[],
            outcome="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_code="tutor_unavailable",
        )
        session.commit()
        raise ApiError(
            503,
            "tutor_unavailable",
            "The tutor could not prepare the review. It did not count.",
        ) from None
    return review, True


def _create(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    ai: InEffect,
    tutor_settings: TutorSettings,
    submission: ExerciseSubmission,
    repeated: schemas.RepeatedMistake,
    started: float,
) -> schemas.MistakeReview:
    error_type = session.get(ErrorType, repeated.error_type)
    assert error_type is not None  # repeated mistakes only have taxonomy codes
    topic = f"\n{repeated.topic_name}" if repeated.topic_name else ""
    hits = retrieve(
        session,
        llm,
        submission.course_id,
        f"{error_type.label_es}: {error_type.description_es}{topic}\n"
        f"{submission.problem_statement}\n{submission.worked_answer}",
        ai.retrieval.top_k,
        ai.retrieval.min_similarity,
    )
    result: ChatResult | None = None
    review: Review | None = None
    if hits:
        result = llm.chat_json(
            build_review_prompt(settings, tutor_settings, ai.instruction("review")),
            build_review_messages(hits, error_type, repeated.topic_name, submission),
            task="review",
            route=ai.route("review"),
        )
        review = validate_review(result.data, len(hits), submission.problem_statement)

    row = MistakeReview(
        submission_id=submission.id,
        course_id=submission.course_id,
        student_id=submission.student_id,
        error_type=repeated.error_type,
        topic_name=repeated.topic_name,
        kind="answer" if review else "no_source",
        explanation=review.explanation
        if review
        else load_labels("messages", settings.tutor_language)["review_no_source"],
        worked_example=review.worked_example if review else None,
        practice=review.practice if review else [],
    )
    session.add(row)
    session.flush()
    cited = [hits[i] for i in review.cited_indexes] if review else []
    session.add_all(
        Citation(
            review_id=row.id,
            fragment_id=hit.fragment.id,
            document_name=hit.document_name,
            location_label=hit.fragment.location_label,
            position=position,
        )
        for position, hit in enumerate(cited, start=1)
    )
    interactions.record(
        session,
        settings,
        course_id=submission.course_id,
        student_id=submission.student_id,
        kind="review",
        question=submission.problem_statement,
        fragment_ids=[hit.fragment.id for hit in hits],
        outcome=row.kind,
        answer=row.explanation,
        model=result.model if result else None,
        input_tokens=result.input_tokens if result else 0,
        output_tokens=result.output_tokens if result else 0,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    session.flush()
    session.refresh(row)
    return review_view(row)
