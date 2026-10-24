"""Exercise feedback (S4). v1 is a contract-honoring stub (FR-100, research R17):
every step is real except the model call, which waits for the error taxonomy."""

import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import not_found
from app.llm.client import LLMClient, LLMError
from app.models import (
    Citation,
    Enrolment,
    ExerciseSubmission,
    LearningRecordEntry,
    Topic,
)
from app.schemas import exercises as schemas
from app.schemas.chat import Correction
from app.services import interactions, tutor
from app.services.retrieval import Hit, retrieve

STUB_ERROR_TYPE = "placeholder"
STUB_EXPLANATION = (
    "Respuesta de ejemplo: la corrección automática de ejercicios aún no está "
    "disponible. Revisa el primer paso con el material citado."
)


def submission_view(submission: ExerciseSubmission) -> schemas.StudentSubmission:
    flag = submission.flag
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
    tutor.ensure_can_message(session, settings, enrolment, request_solution=False)
    # The reservation stands even without a model call: feedback is always given.
    tutor.reserve_or_raise(session, settings, enrolment.student_id)
    started = time.perf_counter()
    try:
        hits = retrieve(
            session,
            llm,
            enrolment.course_id,
            problem_statement,
            settings.retrieval_top_k,
            settings.retrieval_min_similarity,
        )
    except LLMError:
        # Citations are optional in the stub; the feedback still works.
        hits = []
    cited: list[Hit] = hits[:1]
    topic = session.scalar(
        select(Topic)
        .where(Topic.course_id == enrolment.course_id)
        .order_by(Topic.position)
        .limit(1)
    )
    submission = ExerciseSubmission(
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        problem_statement=problem_statement,
        worked_answer=worked_answer,
        verdict="incorrect",
        mistake_location="Paso 1",
        error_type=STUB_ERROR_TYPE,
        topic_id=topic.id if topic else None,
        topic_name=topic.name if topic else None,
        explanation=STUB_EXPLANATION if cited else tutor.no_source_text(settings),
        explanation_kind="answer" if cited else "no_source",
        saved_to_record=True,
        is_stub=True,
    )
    session.add(submission)
    session.flush()
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
    session.add(
        LearningRecordEntry(
            course_id=enrolment.course_id,
            student_id=enrolment.student_id,
            submission_id=submission.id,
            error_type=STUB_ERROR_TYPE,
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
        outcome="stub",
        answer=submission.explanation,
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
