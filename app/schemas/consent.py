from datetime import datetime

from pydantic import BaseModel, Field

from app.core.types import ConsentAction


class Consent(BaseModel):
    given: bool = Field(description="Given for the current version.")
    version: str | None = Field(description="Version of the latest consent given.")
    given_at: datetime | None
    current_version: str


class ConsentEvent(BaseModel):
    action: ConsentAction
    version: str
    created_at: datetime
