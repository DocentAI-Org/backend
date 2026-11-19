import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.core.types import Audience, QuestionnaireStatus
from app.schemas.common import ApiModel, CleanText


def _title(title: str) -> str:
    title = title.strip()
    if not 1 <= len(title) <= 200:
        raise ValueError("The title must have 1 to 200 characters.")
    return title


def _https(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError("The link must be an https address.")
    return url


Title = Annotated[CleanText, AfterValidator(_title)]
Link = Annotated[CleanText, StringConstraints(max_length=2000), AfterValidator(_https)]


class QuestionnaireCreate(BaseModel):
    title: Title
    url: Link = Field(
        description="https link; `{study_ref}` becomes the student's export code."
    )
    audience: Audience


class QuestionnaireUpdate(BaseModel):
    title: Title | None = None
    url: Link | None = None
    status: QuestionnaireStatus | None = None


class Questionnaire(ApiModel):
    id: uuid.UUID
    title: str
    url: str
    audience: Audience
    status: QuestionnaireStatus
    created_at: datetime
    updated_at: datetime


class MyQuestionnaire(BaseModel):
    """An open questionnaire for the caller, with its link resolved."""

    id: uuid.UUID
    title: str
    url: str
