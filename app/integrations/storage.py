"""Supabase Storage REST calls for the private course-material bucket (research R9)."""

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.core.config import Settings, get_settings


class StorageError(Exception):
    pass


class StorageClient(Protocol):
    def upload(self, path: str, content: bytes, content_type: str) -> None: ...

    def download(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...

    def signed_url(self, path: str, ttl_seconds: int) -> tuple[str, datetime]: ...


class SupabaseStorage:
    def __init__(self, settings: Settings) -> None:
        self._base = f"{settings.supabase_url.rstrip('/')}/storage/v1"
        self._bucket = settings.storage_bucket
        key = settings.supabase_service_role_key or ""
        self._headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def _object_url(self, path: str) -> str:
        return f"{self._base}/object/{self._bucket}/{quote(path)}"

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                url,
                headers={**self._headers, **(headers or {})},
                timeout=60,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise StorageError(str(exc)) from exc
        if response.status_code >= 400:
            raise StorageError(f"Storage returned {response.status_code}.")
        return response

    def upload(self, path: str, content: bytes, content_type: str) -> None:
        self._request(
            "POST",
            self._object_url(path),
            headers={"Content-Type": content_type, "x-upsert": "true"},
            content=content,
        )

    def download(self, path: str) -> bytes:
        return self._request("GET", self._object_url(path)).content

    def delete(self, path: str) -> None:
        self._request(
            "DELETE", f"{self._base}/object/{self._bucket}", json={"prefixes": [path]}
        )

    def signed_url(self, path: str, ttl_seconds: int) -> tuple[str, datetime]:
        response = self._request(
            "POST",
            f"{self._base}/object/sign/{self._bucket}/{quote(path)}",
            json={"expiresIn": ttl_seconds},
        )
        # Storage returns a path relative to /storage/v1, e.g. "/object/sign/...".
        signed_path = response.json()["signedURL"]
        return f"{self._base}{signed_path}", datetime.now(UTC) + timedelta(
            seconds=ttl_seconds
        )


@lru_cache
def _default_storage() -> SupabaseStorage:
    return SupabaseStorage(get_settings())


def get_storage() -> StorageClient:
    return _default_storage()
