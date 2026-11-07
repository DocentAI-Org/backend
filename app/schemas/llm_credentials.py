"""Keys for commercial models stored in the app (specs/019); the key is write-only."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, SecretStr, model_validator

from app.core.config import Provider

CredentialProvider = Literal["openai", "anthropic", "openai_compatible"]


class CredentialCreate(BaseModel):
    provider: CredentialProvider
    label: str = Field(min_length=1, max_length=80)
    base_url: HttpUrl | None = Field(
        default=None, description="Required for an OpenAI-compatible API."
    )
    api_key: SecretStr = Field(min_length=8, max_length=500)

    @model_validator(mode="after")
    def address(self) -> "CredentialCreate":
        if self.provider == "openai_compatible" and self.base_url is None:
            raise ValueError("An OpenAI-compatible API needs its base_url.")
        return self


class CredentialUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    offered_models: list[str] | None = Field(
        default=None, description="Models courses may use; omitted keeps them."
    )


class Credential(BaseModel):
    id: uuid.UUID
    provider: CredentialProvider
    label: str
    base_url: str | None
    key_hint: str = Field(description="The last four characters, e.g. …cdef.")
    scope: Literal["study", "course"]
    offered_models: list[str] | None = Field(
        description="The study's: the models courses may use; null is all."
    )
    created_at: datetime


class ServerKey(BaseModel):
    provider: Provider
    label: str


class StudyCredentials(BaseModel):
    server: list[ServerKey] = Field(
        description="Providers the server's environment has."
    )
    items: list[Credential]
