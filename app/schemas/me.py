import uuid
from typing import Literal

from pydantic import BaseModel

from app.core.types import Language, Role
from app.models import Profile
from app.schemas.common import ApiModel


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    database: Literal["ok", "error"]
    llm: Literal["ok", "error"]


class Me(ApiModel):
    id: uuid.UUID
    role: Role
    display_name: str
    email: str | None
    is_pseudonymous: bool
    preferred_language: Language

    @classmethod
    def from_profile(cls, profile: Profile) -> "Me":
        return cls(
            id=profile.id,
            role=profile.role,  # type: ignore[arg-type]
            display_name=profile.display_name,
            email=profile.email,
            is_pseudonymous=profile.pseudonym_code is not None,
            preferred_language=profile.preferred_language,  # type: ignore[arg-type]
        )


class MeUpdate(BaseModel):
    preferred_language: Language
