"""A suggested topic for each section of the material (specs/024, FR-073 of spec 001).

A section is compared with the course's topic names through embeddings: the mean of
its fragments' vectors and, when it is named by a heading, of its heading's, against
each name's vector. The heading counts as much as the text: Word and Markdown leave it
out of the fragments, and it is the closest thing to a topic name the material has.
The closest topic is suggested when it reaches the threshold. Suggestions never
count until the teacher confirms them, and never touch a confirmed assignment.
"""

import logging
import math
import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionFactory
from app.llm.client import LLMClient, LLMError
from app.models import Document, Fragment, Topic, TopicAssignment
from app.services.parsing import PREFACE_SECTION

logger = logging.getLogger(__name__)

Vector = list[float]


def suggest_for_document(
    session_factory: SessionFactory, llm: LLMClient, document_id: uuid.UUID
) -> None:
    """Background: suggestions for a document that has just been processed."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is not None:
            _refresh(session, llm, document.course_id, [document_id])


def suggest_for_course(
    session_factory: SessionFactory, llm: LLMClient, course_id: uuid.UUID
) -> None:
    """Background: suggestions for the course's material, after its topics change."""
    with session_factory() as session:
        _refresh(session, llm, course_id, None)


def _refresh(
    session: Session,
    llm: LLMClient,
    course_id: uuid.UUID,
    document_ids: Sequence[uuid.UUID] | None,
) -> None:
    try:
        suggestions = _suggestions(session, llm, course_id, document_ids)
    except LLMError:
        # Kept as they were; the next document or topic change recomputes them.
        logger.warning("Topic suggestions skipped for course %s", course_id)
        return
    except Exception:
        # Suggestions are a help: the material and topics are saved either way.
        logger.exception("Topic suggestions failed for course %s", course_id)
        return
    if suggestions is None:
        return
    targets, rows = suggestions
    session.execute(
        delete(TopicAssignment).where(
            TopicAssignment.document_id.in_(targets),
            TopicAssignment.status == "suggested",
        )
    )
    session.add_all(rows)
    session.commit()


def _suggestions(
    session: Session,
    llm: LLMClient,
    course_id: uuid.UUID,
    document_ids: Sequence[uuid.UUID] | None,
) -> tuple[list[uuid.UUID], list[TopicAssignment]] | None:
    """The documents whose suggestions are replaced and the new ones, or None when
    there is nothing to compare."""
    query = select(Document.id).where(
        Document.course_id == course_id, Document.processing_status == "ready"
    )
    if document_ids is not None:
        query = query.where(Document.id.in_(document_ids))
    targets = list(session.scalars(query))
    topics = session.scalars(select(Topic).where(Topic.course_id == course_id)).all()
    if not targets or not topics:
        return None

    confirmed = session.execute(
        select(TopicAssignment.document_id, TopicAssignment.section).where(
            TopicAssignment.document_id.in_(targets),
            TopicAssignment.status == "confirmed",
        )
    ).all()
    whole = {document for document, section in confirmed if section is None}
    sections = {(document, section) for document, section in confirmed if section}
    open_sections = {
        key: vector
        for key, vector in _section_vectors(session, targets).items()
        if key[0] not in whole and key not in sections
    }
    if not open_sections:
        return targets, []

    headings = sorted({section for _, section in open_sections if _is_heading(section)})
    heading_vectors = dict(
        zip(headings, llm.embed(headings) if headings else [], strict=True)
    )
    names = llm.embed([topic.name for topic in topics])
    threshold = get_settings().topic_suggestion_min_similarity
    rows = []
    for (document_id, section), content in open_sections.items():
        heading = heading_vectors.get(section)
        vector = content if heading is None else _mean([content, heading])
        similarity, topic = max(
            (
                (_cosine(vector, name), topic)
                for name, topic in zip(names, topics, strict=True)
            ),
            key=lambda pair: pair[0],
        )
        if similarity >= threshold:
            rows.append(
                TopicAssignment(
                    course_id=course_id,
                    topic_id=topic.id,
                    document_id=document_id,
                    section=section,
                    status="suggested",
                )
            )
    return targets, rows


def _section_vectors(
    session: Session, document_ids: list[uuid.UUID]
) -> dict[tuple[uuid.UUID, str], Vector]:
    """The mean of each section's fragment vectors."""
    sums: dict[tuple[uuid.UUID, str], Vector] = {}
    counts: defaultdict[tuple[uuid.UUID, str], int] = defaultdict(int)
    rows = session.execute(
        select(Fragment.document_id, Fragment.section, Fragment.embedding).where(
            Fragment.document_id.in_(document_ids),
            Fragment.excluded.is_(False),
            Fragment.embedding.is_not(None),
        )
    )
    for document_id, section, embedding in rows:
        key = (document_id, section)
        values = [float(v) for v in embedding or ()]
        if key in sums:
            sums[key] = [a + b for a, b in zip(sums[key], values, strict=True)]
        else:
            sums[key] = values
        counts[key] += 1
    return {key: [v / counts[key] for v in total] for key, total in sums.items()}


def _is_heading(section: str) -> bool:
    """Named by the material rather than by a page number or as the preface."""
    return not section.isdigit() and section != PREFACE_SECTION


def _mean(vectors: list[Vector]) -> Vector:
    return [sum(column) / len(vectors) for column in zip(*vectors, strict=True)]


def _cosine(a: Vector, b: Vector) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0
