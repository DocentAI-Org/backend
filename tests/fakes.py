"""Deterministic stand-ins for the model provider, Storage and Auth admin."""

import hashlib
import math
import re
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.llm.client import ChatResult, LLMError

DIMENSIONS = 1024
_WORD = re.compile(r"[a-z0-9]{3,}")


def _words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    return _WORD.findall(ascii_only)


def hashed_embedding(value: str) -> list[float]:
    """Bag-of-words vector: texts sharing words are similar, unrelated texts are not."""
    vector = [0.0] * DIMENSIONS
    for word in _words(value):
        index = int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIMENSIONS
        vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


class FakeLLM:
    chat_model = "fake-model"

    def __init__(self) -> None:
        self.reply: (
            dict[str, Any] | Callable[[str, list[dict[str, str]]], dict[str, Any]]
        ) = {
            "kind": "answer",
            "text": "Según el material, se resta 3 y se divide entre 2.",
            "cited": ["F1"],
        }
        self.fail_chat = False
        self.fail_embed = False
        self.reachable = True
        self.chat_calls: list[tuple[str, list[dict[str, str]]]] = []
        self.temperatures: list[float] = []
        self.tasks: list[str] = []

    def chat_json(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        task: str = "tutor",
    ) -> ChatResult:
        self.chat_calls.append((system, messages))
        self.temperatures.append(temperature)
        self.tasks.append(task)
        if self.fail_chat:
            raise LLMError("fake provider failure")
        data = (
            self.reply(system, messages) if callable(self.reply) else dict(self.reply)
        )
        prompt_chars = len(system) + sum(len(m["content"]) for m in messages)
        return ChatResult(
            data=data,
            model=self.chat_model,
            input_tokens=prompt_chars // 4,
            output_tokens=20,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.fail_embed:
            raise LLMError("fake embedding failure")
        return [hashed_embedding(t) for t in texts]

    def is_reachable(self) -> bool:
        return self.reachable


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, path: str, content: bytes, content_type: str) -> None:
        self.objects[path] = content

    def download(self, path: str) -> bytes:
        return self.objects[path]

    def delete(self, path: str) -> None:
        self.objects.pop(path, None)

    def signed_url(self, path: str, ttl_seconds: int) -> tuple[str, datetime]:
        return (
            f"http://storage.test/signed/{path}?token=fake",
            datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )


def insert_auth_user(
    session: Session, email: str | None, display_name: str
) -> uuid.UUID:
    """Inserts a row in auth.users; the handle_new_user trigger creates the profile."""
    user_id = uuid.uuid4()
    session.execute(
        text(
            "insert into auth.users (id, aud, role, email, raw_user_meta_data, "
            "created_at, updated_at) values (:id, 'authenticated', 'authenticated', "
            ":email, "
            "jsonb_build_object('display_name', cast(:name as text)), now(), now())"
        ),
        {"id": user_id, "email": email, "name": display_name},
    )
    return user_id


class FakeAuthAdmin:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.created: list[str] = []
        self.deleted: list[uuid.UUID] = []
        self.fail_with: Exception | None = None

    def create_user(self, email: str, password: str, display_name: str) -> uuid.UUID:
        with self._session_factory() as session:
            user_id = insert_auth_user(session, email, display_name)
            session.commit()
        self.created.append(email)
        return user_id

    def delete_user(self, user_id: uuid.UUID) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        with self._session_factory() as session:
            session.execute(
                text("delete from auth.users where id = :id"), {"id": user_id}
            )
            session.commit()
        self.deleted.append(user_id)
