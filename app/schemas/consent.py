from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Consent(BaseModel):
    given: bool = Field(description="Given for the current version.")
    version: str | None = Field(description="Version of the latest consent given.")
    given_at: datetime | None
    current_version: str


class ConsentEvent(BaseModel):
    action: Literal["given", "revoked"]
    version: str
    created_at: datetime
