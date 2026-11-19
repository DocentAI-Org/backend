"""Course material: upload, background processing and validation (T2)."""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Literal, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.errors import ApiError, not_found
from app.core.search import matches
from app.integrations.storage import StorageClient, StorageError
from app.llm.client import LLMClient, LLMError
from app.models import Course, Document, Fragment, Profile, TopicAssignment
from app.schemas import documents as schemas
from app.services.chunking import chunk_sections
from app.services.parsing import (
    CONTENT_TYPES,
    ParsingError,
    detect_file_type,
    parse_document,
)

logger = logging.getLogger(__name__)
EMBEDDING_BATCH = 32
STORAGE_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "markdown": "md"}


def get_course_document(
    session: Session, course: Course, document_id: uuid.UUID
) -> Document:
    document = session.get(Document, document_id)
    if document is None or document.course_id != course.id:
        raise not_found("Document")
    return document


def to_schema(session: Session, document: Document) -> schemas.Document:
    total, excluded = session.execute(
        select(
            func.count(Fragment.id),
            func.count(Fragment.id).filter(Fragment.excluded.is_(True)),
        ).where(Fragment.document_id == document.id)
    ).one()
    topics = session.scalars(
        select(TopicAssignment).where(
            TopicAssignment.document_id == document.id,
            TopicAssignment.status == "confirmed",
        )
    ).all()
    unique_topics = {a.topic.id: a.topic for a in topics}
    return schemas.Document(
        id=document.id,
        file_name=document.file_name,
        file_type=document.file_type,  # type: ignore[arg-type]
        size_bytes=document.size_bytes,
        page_count=document.page_count,
        processing_status=document.processing_status,  # type: ignore[arg-type]
        error_reason=document.error_reason,  # type: ignore[arg-type]
        validation_status=document.validation_status,  # type: ignore[arg-type]
        validated_by_name=document.validator.display_name
        if document.validator
        else None,
        validated_at=document.validated_at,
        fragment_count=total,
        excluded_fragment_count=excluded,
        uploaded_at=document.uploaded_at,
        topics=[
            schemas.TopicRef(id=t.id, name=t.name)
            for t in sorted(unique_topics.values(), key=lambda t: t.position)
        ],
    )


def store_upload(
    session: Session,
    storage: StorageClient,
    settings: Settings,
    course: Course,
    teacher: Profile,
    file_name: str,
    content: bytes,
) -> Document:
    file_type = detect_file_type(file_name)
    if file_type is None:
        raise ApiError(
            415, "unsupported_file_type", "Only PDF, DOCX and Markdown are accepted."
        )
    if len(content) > settings.max_upload_bytes:
        raise ApiError(
            413,
            "file_too_large",
            f"Files are limited to {settings.max_upload_mb} MB.",
            {"max_mb": settings.max_upload_mb},
        )
    # Only the base name is kept, and it never reaches the storage key: a name
    # such as "../../x" must not address another object in the bucket.
    display_name = PurePath(file_name.replace("\\", "/")).name.strip() or "documento"
    document = Document(
        id=uuid.uuid4(),
        course_id=course.id,
        file_name=display_name[:255],
        file_type=file_type,
        size_bytes=len(content),
        storage_path="",
        uploaded_by=teacher.id,
    )
    document.storage_path = f"{course.id}/{document.id}.{STORAGE_EXTENSIONS[file_type]}"
    try:
        storage.upload(document.storage_path, content, CONTENT_TYPES[file_type])
    except StorageError as exc:
        raise ApiError(
            503, "storage_unavailable", "File storage is unavailable."
        ) from exc
    session.add(document)
    session.flush()
    session.refresh(document)
    return document


def process_document(
    session_factory: SessionFactory,
    llm: LLMClient,
    document_id: uuid.UUID,
    file_type: str,
    content: bytes,
) -> None:
    """Background task: parse, chunk, embed and store fragments."""
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is None:
            return
        try:
            parsed = parse_document(file_type, content)
            chunks = chunk_sections(parsed.sections)
            vectors: list[list[float]] = []
            for start in range(0, len(chunks), EMBEDDING_BATCH):
                batch = chunks[start : start + EMBEDDING_BATCH]
                vectors.extend(llm.embed([c.text for c in batch]))
        except ParsingError as exc:
            _mark_error(session, document_id, exc.reason)
            return
        except LLMError:
            logger.warning("Embedding failed for document %s", document_id)
            _mark_error(session, document_id, "processing_failed")
            return
        except Exception:
            logger.exception("Processing failed for document %s", document_id)
            _mark_error(session, document_id, "processing_failed")
            return

        # The teacher may have deleted the document while it was processing.
        if session.get(Document, document_id, populate_existing=True) is None:
            return
        session.add_all(
            Fragment(
                document_id=document_id,
                course_id=document.course_id,
                position=position,
                section=chunk.section,
                location_label=chunk.location_label,
                text=chunk.text,
                embedding=vector,
            )
            for position, (chunk, vector) in enumerate(
                zip(chunks, vectors, strict=True), start=1
            )
        )
        document.page_count = parsed.page_count
        document.processing_status = "ready"
        document.error_reason = None
        try:
            session.commit()
        except Exception:
            logger.exception("Storing fragments failed for document %s", document_id)
            session.rollback()
            _mark_error(session, document_id, "processing_failed")


def _mark_error(session: Session, document_id: uuid.UUID, reason: str) -> None:
    session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(processing_status="error", error_reason=reason)
    )
    session.commit()


def recover_interrupted(session: Session) -> int:
    """Documents left in `processing` by a restart cannot finish; flag them."""
    result = cast(
        CursorResult,
        session.execute(
            update(Document)
            .where(Document.processing_status == "processing")
            .values(processing_status="error", error_reason="processing_interrupted")
        ),
    )
    session.commit()
    return result.rowcount or 0


def _require_ready(document: Document) -> None:
    if document.processing_status != "ready":
        raise ApiError(
            409, "document_not_ready", "Only processed documents can be reviewed."
        )


def validate(session: Session, document: Document, teacher: Profile) -> Document:
    _require_ready(document)
    document.validation_status = "validated"
    document.validated_by = teacher.id
    document.validated_at = datetime.now(UTC)
    session.flush()
    session.refresh(document)
    return document


def exclude(session: Session, document: Document) -> Document:
    _require_ready(document)
    document.validation_status = "excluded"
    session.flush()
    return document


def delete(session: Session, storage: StorageClient, document: Document) -> None:
    path = document.storage_path
    session.delete(document)
    session.flush()
    try:
        storage.delete(path)
    except StorageError:
        logger.warning("Could not delete stored file for document %s", document.id)


DocumentSort = Literal["recent", "name"]


def list_documents(
    session: Session,
    course: Course,
    limit: int,
    offset: int,
    q: str | None = None,
    sort: DocumentSort = "recent",
) -> tuple[list[Document], int]:
    query = select(Document).where(
        Document.course_id == course.id, matches(q, Document.file_name)
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    order = (
        (func.lower(Document.file_name), Document.id)
        if sort == "name"
        else (Document.uploaded_at.desc(), Document.id)
    )
    rows = session.scalars(query.order_by(*order).limit(limit).offset(offset)).all()
    return list(rows), total


def list_fragments(
    session: Session, document: Document, limit: int, offset: int
) -> tuple[list[Fragment], int]:
    query = select(Fragment).where(Fragment.document_id == document.id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Fragment.position).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def get_fragment(
    session: Session, document: Document, fragment_id: uuid.UUID
) -> Fragment:
    fragment = session.get(Fragment, fragment_id)
    if fragment is None or fragment.document_id != document.id:
        raise not_found("Fragment")
    return fragment


def signed_url(
    storage: StorageClient, settings: Settings, document: Document
) -> schemas.SignedUrl:
    try:
        url, expires_at = storage.signed_url(
            document.storage_path, settings.signed_url_ttl_seconds
        )
    except StorageError as exc:
        raise ApiError(
            503, "storage_unavailable", "File storage is unavailable."
        ) from exc
    return schemas.SignedUrl(url=url, expires_at=expires_at)
