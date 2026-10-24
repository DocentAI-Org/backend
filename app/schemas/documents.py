import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

FileType = Literal["pdf", "docx", "markdown"]
ProcessingStatus = Literal["processing", "ready", "error"]
ValidationStatus = Literal["pending_validation", "validated", "excluded"]
ErrorReason = Literal[
    "unsupported_format",
    "no_readable_text",
    "processing_failed",
    "processing_interrupted",
]


class TopicRef(BaseModel):
    id: uuid.UUID
    name: str


class Document(BaseModel):
    id: uuid.UUID
    file_name: str
    file_type: FileType
    size_bytes: int
    page_count: int | None
    processing_status: ProcessingStatus
    error_reason: ErrorReason | None
    validation_status: ValidationStatus
    validated_by_name: str | None
    validated_at: datetime | None
    fragment_count: int
    excluded_fragment_count: int
    uploaded_at: datetime
    topics: list[TopicRef]


class Fragment(BaseModel):
    id: uuid.UUID
    position: int
    section: str
    location_label: str
    text: str
    excluded: bool


class FragmentUpdate(BaseModel):
    excluded: bool


class SignedUrl(BaseModel):
    url: str
    expires_at: datetime
