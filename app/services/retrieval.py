"""Retrieval over validated material only (constitution I, FR-034, research R5)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.models import Document, Fragment


@dataclass(frozen=True)
class Hit:
    fragment: Fragment
    document_name: str
    similarity: float


def retrievable_fragment_filter():
    return (
        Fragment.excluded.is_(False),
        Fragment.embedding.is_not(None),
        Document.processing_status == "ready",
        Document.validation_status == "validated",
    )


def retrieve(
    session: Session,
    llm: LLMClient,
    course_id: uuid.UUID | str,
    question: str,
    top_k: int,
    min_similarity: float,
) -> list[Hit]:
    [query_vector] = llm.embed([question])
    distance = Fragment.embedding.cosine_distance(query_vector)
    rows = session.execute(
        select(Fragment, Document.file_name, distance.label("distance"))
        .join(Document, Document.id == Fragment.document_id)
        .where(Fragment.course_id == course_id, *retrievable_fragment_filter())
        .order_by(distance, Fragment.id)
        .limit(top_k)
    ).all()
    hits = [
        Hit(fragment=fragment, document_name=name, similarity=1 - float(dist))
        for fragment, name, dist in rows
    ]
    return [hit for hit in hits if hit.similarity >= min_similarity]
