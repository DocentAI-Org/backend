"""A credential the app may use for a commercial model (specs/019). The key is decrypted
only to call the provider and never printed."""

import uuid
from dataclasses import dataclass, field

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Provider


@dataclass(frozen=True)
class CredentialAccess:
    id: uuid.UUID
    provider: Provider
    label: str
    base_url: str | None
    api_key: str = field(repr=False)


def encrypt(master_key: str, api_key: str) -> str:
    return Fernet(master_key.encode()).encrypt(api_key.encode()).decode()


def decrypt(master_key: str, token: str) -> str:
    try:
        return Fernet(master_key.encode()).decrypt(token.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - the master key changed
        raise RuntimeError(
            "A stored key cannot be decrypted with LLM_CREDENTIALS_KEY."
        ) from exc
