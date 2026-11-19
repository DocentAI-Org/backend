import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.core.types import AssignmentStatus
from app.schemas.common import CleanText


class TopicCreate(BaseModel):
    name: CleanText = Field(min_length=1, max_length=60)


class TopicUpdate(TopicCreate):
    pass


class TopicOrder(BaseModel):
    topic_ids: list[uuid.UUID] = Field(
        description="Every topic of the course, in order."
    )


class Topic(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    assignment_count: int


class TopicAssignmentCreate(BaseModel):
    topic_id: uuid.UUID
    document_id: uuid.UUID
    section: str | None = Field(
        default=None, description="Section of the document; omit for the whole one."
    )


class TopicAssignmentUpdate(BaseModel):
    topic_id: uuid.UUID | None = None
    status: Literal["confirmed"] = "confirmed"


class TopicAssignment(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    topic_name: str
    document_id: uuid.UUID
    document_name: str
    section: str | None
    status: AssignmentStatus


class UnassignedDocument(BaseModel):
    document_id: uuid.UUID
    document_name: str
    sections: list[str] = Field(description="Sections without a confirmed topic.")
