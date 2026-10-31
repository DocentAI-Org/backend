"""Exercise feedback (S4, specs/003): the model judges a worked answer against the
course material, classifies the first mistake with the error taxonomy and the course
topics, and mistakes go to the student's learning record."""

import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError, not_found
from app.llm.client import ChatResult, LLMClient, LLMError
from app.llm.prompts import load_labels, load_prompt
from app.models import (
    Citation,
    Enrolment,
    ErrorType,
    ExerciseSubmission,
    LearningRecordEntry,
    Topic,
    TopicAssignment,
    TutorSettings,
)
from app.schemas import exercises as schemas
from app.schemas.chat import Adaptation, Correction
from app.services import adaptation, allowance, interactions, pedagogy, tutor
from app.services.retrieval import Hit, retrieve

logger = logging.getLogger(__name__)

GRADED_VERDICTS = {"correct", "partially_correct", "incorrect"}
_TOPIC_REF = re.compile(r"T([0-9]{1,3})", re.IGNORECASE)
# Small models write "F1" in the text despite the prompt; students only see citations.
_REFS = r"F[0-9]{1,3}(?:\s*(?:,|y)\s*F[0-9]{1,3})*"
_REF_CLEANUP = [
    (re.compile(rf"\s*[;,]?\s*\b(?:ver|véase)\s+{_REFS}", re.IGNORECASE), ""),
    (re.compile(rf"\s*\(\s*{_REFS}\s*\)"), ""),
    (re.compile(rf"\b(?:el\s+)?(?:fragmento\s+)?{_REFS}\b"), "el material"),
]
_CONTRACTIONS = re.compile(r"\b([Dd]e|[Aa]) el (?=material\b)")
LOCATION_CHARS = 300


@dataclass
class Feedback:
    verdict: str
    explanation: str
    cited_indexes: list[int]
    mistake_location: str | None = None
    error_type: str | None = None
    topic_index: int | None = None
    # A mistake whose type is missing or not in the taxonomy (FR-006).
    unclassified: bool = False


def validate_feedback(
    data: dict, fragment_count: int, topic_count: int, codes: set[str]
) -> Feedback | None:
    """Accepts the model's feedback only if it is graded and grounded (FR-002).

    Returns None for anything unusable; unknown error types and topics are dropped.
    """
    verdict = data.get("verdict")
    explanation = data.get("explanation")
    cited = data.get("cited")
    if verdict not in GRADED_VERDICTS or not isinstance(cited, list):
        return None
    if not isinstance(explanation, str) or not explanation.strip():
        return None
    indexes = tutor.cited_fragment_indexes(cited, fragment_count)
    if not indexes:
        return None
    feedback = Feedback(verdict, without_fragment_refs(explanation), indexes)
    # Every graded exercise keeps its topic, so progress can count it (spec 007 FR-005).
    topic = data.get("topic")
    match = _TOPIC_REF.fullmatch(topic) if isinstance(topic, str) else None
    if match and 0 < int(match.group(1)) <= topic_count:
        feedback.topic_index = int(match.group(1)) - 1
    if verdict == "correct":
        return feedback
    location = data.get("mistake_location")
    if isinstance(location, str) and location.strip():
        feedback.mistake_location = location.strip()[:LOCATION_CHARS]
    error_type = data.get("error_type")
    if isinstance(error_type, str) and error_type in codes:
        feedback.error_type = error_type
    else:
        feedback.unclassified = True
    return feedback


def without_fragment_refs(text: str) -> str:
    for pattern, replacement in _REF_CLEANUP:
        text = pattern.sub(replacement, text)
    # "de F1" became "de el material": contract it as Spanish does.
    text = _CONTRACTIONS.sub(lambda m: f"{m.group(1)}l ", text)
    return text.strip()


def build_feedback_prompt(
    settings: Settings, tutor_settings: TutorSettings, note: str | None = None
) -> str:
    """The note (spec 013) is one more rule, before the reply format: after it, a
    small model drops "cited"."""
    labels = load_labels("policies", settings.tutor_language)
    rule = (
        "feedback.solution_allowed"
        if tutor_settings.solution_policy == "direct"
        else "feedback.no_solution"
    )
    return load_prompt("exercise_feedback", settings.tutor_language).format(
        level=labels[f"level.{tutor_settings.level}"],
        tone=labels[f"tone.{tutor_settings.tone}"],
        solution_rule=labels[rule],
        adaptation=f"\n6. {note}" if note else "",
    )


def fragment_topic_refs(
    session: Session, hits: list[Hit], topics: list[Topic]
) -> list[str | None]:
    """The topic (T1, T2...) of each fragment from confirmed assignments; a section
    assignment wins over one for the whole document (spec 009 FR-002)."""
    refs = {topic.id: f"T{i}" for i, topic in enumerate(topics, start=1)}
    assignments = session.execute(
        select(
            TopicAssignment.topic_id,
            TopicAssignment.document_id,
            TopicAssignment.section,
        ).where(
            TopicAssignment.document_id.in_({h.fragment.document_id for h in hits}),
            TopicAssignment.status == "confirmed",
        )
    ).all()
    by_section = {(doc, section): t for t, doc, section in assignments if section}
    by_document = {doc: t for t, doc, section in assignments if section is None}
    result = []
    for hit in hits:
        fragment = hit.fragment
        topic_id = by_section.get(
            (fragment.document_id, fragment.section)
        ) or by_document.get(fragment.document_id)
        result.append(refs.get(topic_id) if topic_id else None)
    return result


def build_feedback_messages(
    hits: list[Hit],
    topics: list[Topic],
    error_types: list[ErrorType],
    problem_statement: str,
    worked_answer: str,
    topic_refs: list[str | None] | None = None,
) -> list[dict[str, str]]:
    """Only course material, topic names, the taxonomy and the exercise (FR-007)."""
    topic_list = "\n".join(
        f'<tema id="T{i}">{topic.name}</tema>'
        for i, topic in enumerate(topics, start=1)
    )
    type_list = "\n".join(
        f'<tipo codigo="{t.code}">{t.label_es}: {t.description_es}</tipo>'
        for t in error_types
    )
    return [
        {
            "role": "user",
            "content": f"{tutor.material_block(hits, topic_refs)}\n\n"
            f"<temas>\n{topic_list}\n</temas>\n\n"
            f"<tipos_de_error>\n{type_list}\n</tipos_de_error>\n\n"
            f"<enunciado>\n{problem_statement}\n</enunciado>\n\n"
            f"<respuesta>\n{worked_answer}\n</respuesta>",
        }
    ]


def repeated_mistake(
    session: Session, settings: Settings, submission: ExerciseSubmission
) -> schemas.RepeatedMistake | None:
    """The pattern this submission's mistake repeats, counted up to it (spec 005)."""
    entry = session.scalar(
        select(LearningRecordEntry).where(
            LearningRecordEntry.submission_id == submission.id
        )
    )
    if entry is None:
        return None
    threshold = pedagogy.in_effect(session, entry.course_id).criteria.repeated_mistakes
    window = timedelta(days=threshold.window_days)
    same_topic = (
        LearningRecordEntry.topic_id == entry.topic_id
        if entry.topic_id is not None
        else LearningRecordEntry.topic_id.is_(None)
        & LearningRecordEntry.topic_name.is_not_distinct_from(entry.topic_name)
    )
    count = session.scalar(
        select(func.count()).where(
            LearningRecordEntry.course_id == entry.course_id,
            LearningRecordEntry.student_id == entry.student_id,
            LearningRecordEntry.error_type == entry.error_type,
            same_topic,
            LearningRecordEntry.created_at <= entry.created_at,
            LearningRecordEntry.created_at > entry.created_at - window,
        )
    )
    if not count or count < threshold.count:
        return None
    return schemas.RepeatedMistake(
        count=count,
        window_days=threshold.window_days,
        error_type=entry.error_type,
        topic_name=entry.topic_name,
    )


def submission_view(submission: ExerciseSubmission) -> schemas.StudentSubmission:
    flag = submission.flag
    session = object_session(submission)
    return schemas.StudentSubmission(
        id=submission.id,
        problem_statement=submission.problem_statement,
        worked_answer=submission.worked_answer,
        verdict=submission.verdict,  # type: ignore[arg-type]
        mistake_location=submission.mistake_location,
        error_type=submission.error_type,
        topic_name=submission.topic_name,
        explanation=submission.explanation,
        explanation_kind=submission.explanation_kind,  # type: ignore[arg-type]
        citations=[tutor.citation_view(c) for c in submission.citations],
        saved_to_record=submission.saved_to_record,
        is_stub=submission.is_stub,
        correction=Correction(text=flag.correction, reviewed_at=flag.updated_at)
        if flag
        else None,
        repeated_mistake=repeated_mistake(session, get_settings(), submission)
        if session is not None and submission.saved_to_record
        else None,
        adaptation=Adaptation(**submission.adaptation)
        if submission.adaptation
        else None,
        created_at=submission.created_at,
    )


def entry_view(entry: LearningRecordEntry) -> schemas.LearningRecordEntry:
    return schemas.LearningRecordEntry(
        id=entry.id,
        submission_id=entry.submission_id,
        error_type=entry.error_type,
        topic_id=entry.topic_id,
        topic_name=entry.topic_name,
        topic_deleted=entry.topic_id is None and entry.topic_name is not None,
        created_at=entry.created_at,
    )


def submit(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    enrolment: Enrolment,
    problem_statement: str,
    worked_answer: str,
) -> schemas.StudentSubmission:
    tutor_settings = tutor.ensure_can_message(
        session, settings, enrolment, request_solution=False
    )
    day = tutor.reserve_or_raise(session, settings, enrolment.student_id)
    session.commit()
    started = time.perf_counter()
    try:
        return _assess(
            session,
            llm,
            settings,
            enrolment,
            tutor_settings,
            problem_statement,
            worked_answer,
            started,
        )
    except Exception as exc:
        # Nothing is stored and the student is not charged (US1 AS6).
        if not isinstance(exc, LLMError):
            logger.exception(
                "Exercise feedback failed in course %s", enrolment.course_id
            )
        session.rollback()
        allowance.release(session, enrolment.student_id, day)
        interactions.record(
            session,
            settings,
            course_id=enrolment.course_id,
            student_id=enrolment.student_id,
            kind="exercise",
            question=problem_statement,
            fragment_ids=[],
            outcome="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_code="tutor_unavailable",
        )
        session.commit()
        raise ApiError(
            503,
            "tutor_unavailable",
            "The tutor could not check the exercise. It did not count.",
        ) from None


def _assess(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    enrolment: Enrolment,
    tutor_settings: TutorSettings,
    problem_statement: str,
    worked_answer: str,
    started: float,
) -> schemas.StudentSubmission:
    hits = retrieve(
        session,
        llm,
        enrolment.course_id,
        f"{problem_statement}\n{worked_answer}",
        settings.retrieval_top_k,
        settings.retrieval_min_similarity_exercises,
    )
    topics = list(
        session.scalars(
            select(Topic)
            .where(Topic.course_id == enrolment.course_id)
            .order_by(Topic.position)
        )
    )
    feedback: Feedback | None = None
    result: ChatResult | None = None
    focus = adaptation.focus(
        session, settings, enrolment.course_id, enrolment.student_id
    )
    if hits:
        system = build_feedback_prompt(
            settings, tutor_settings, adaptation.prompt_note(session, settings, focus)
        )
        error_types = list(
            session.scalars(select(ErrorType).order_by(ErrorType.position))
        )
        result = llm.chat_json(
            system,
            build_feedback_messages(
                hits,
                topics,
                error_types,
                problem_statement,
                worked_answer,
                fragment_topic_refs(session, hits, topics),
            ),
            temperature=settings.llm_feedback_temperature,
            task="feedback",
        )
        feedback = validate_feedback(
            result.data, len(hits), len(topics), {t.code for t in error_types}
        )

    topic = (
        topics[feedback.topic_index]
        if feedback and feedback.topic_index is not None
        else None
    )
    recorded = bool(feedback and feedback.error_type)
    submission = ExerciseSubmission(
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        problem_statement=problem_statement,
        worked_answer=worked_answer,
        verdict=feedback.verdict if feedback else "not_assessed",
        mistake_location=feedback.mistake_location if feedback else None,
        error_type=feedback.error_type if feedback else None,
        topic_id=topic.id if topic else None,
        topic_name=topic.name if topic else None,
        explanation=feedback.explanation
        if feedback
        else tutor.no_source_text(settings),
        explanation_kind="answer" if feedback else "no_source",
        saved_to_record=recorded,
        is_stub=False,
        adaptation=focus.model_dump() if focus and feedback else None,
    )
    session.add(submission)
    session.flush()
    cited = [hits[i] for i in feedback.cited_indexes] if feedback else []
    session.add_all(
        Citation(
            submission_id=submission.id,
            fragment_id=hit.fragment.id,
            document_name=hit.document_name,
            location_label=hit.fragment.location_label,
            position=position,
        )
        for position, hit in enumerate(cited, start=1)
    )
    if recorded:
        session.add(
            LearningRecordEntry(
                course_id=enrolment.course_id,
                student_id=enrolment.student_id,
                submission_id=submission.id,
                error_type=submission.error_type,
                topic_id=submission.topic_id,
                topic_name=submission.topic_name,
            )
        )
    interactions.record(
        session,
        settings,
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        kind="exercise",
        question=problem_statement,
        fragment_ids=[hit.fragment.id for hit in hits],
        outcome="unclassified"
        if feedback and feedback.unclassified
        else submission.verdict,
        answer=submission.explanation,
        model=result.model if result else None,
        input_tokens=result.input_tokens if result else 0,
        output_tokens=result.output_tokens if result else 0,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    session.flush()
    session.refresh(submission)
    return submission_view(submission)


def get_submission(
    session: Session, enrolment: Enrolment, submission_id: uuid.UUID
) -> ExerciseSubmission:
    submission = session.get(ExerciseSubmission, submission_id)
    if (
        submission is None
        or submission.course_id != enrolment.course_id
        or submission.student_id != enrolment.student_id
    ):
        raise not_found("Submission")
    return submission


def list_submissions(
    session: Session,
    course_id: uuid.UUID,
    student_id: uuid.UUID | None,
    limit: int,
    offset: int,
    created_from=None,
    created_to=None,
) -> tuple[list[ExerciseSubmission], int]:
    query = select(ExerciseSubmission).where(ExerciseSubmission.course_id == course_id)
    if student_id:
        query = query.where(ExerciseSubmission.student_id == student_id)
    if created_from:
        query = query.where(ExerciseSubmission.created_at >= created_from)
    if created_to:
        query = query.where(ExerciseSubmission.created_at <= created_to)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(ExerciseSubmission.created_at.desc(), ExerciseSubmission.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def learning_record(
    session: Session,
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[schemas.LearningRecordEntry], int]:
    query = select(LearningRecordEntry).where(
        LearningRecordEntry.course_id == course_id,
        LearningRecordEntry.student_id == student_id,
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(LearningRecordEntry.created_at.desc(), LearningRecordEntry.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [entry_view(e) for e in rows], total
