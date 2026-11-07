"""Supabase Auth admin calls to create and delete accounts (research R8, spec 017)."""

import uuid
from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ApiError


class AuthAdminClient(Protocol):
    def create_user(
        self, email: str, password: str, display_name: str
    ) -> uuid.UUID: ...

    def delete_user(self, user_id: uuid.UUID) -> None: ...


class SupabaseAuthAdmin:
    def __init__(self, settings: Settings) -> None:
        self._url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users"
        key = settings.supabase_service_role_key or ""
        self._headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def create_user(self, email: str, password: str, display_name: str) -> uuid.UUID:
        try:
            response = httpx.post(
                self._url,
                headers=self._headers,
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"display_name": display_name},
                },
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise ApiError(
                503, "auth_unavailable", "The authentication service is unreachable."
            ) from exc
        if response.status_code == 422 or response.status_code == 409:
            raise ApiError(
                409, "email_taken", "An account with this email already exists."
            )
        if response.status_code >= 400:
            raise ApiError(
                503,
                "auth_unavailable",
                f"Authentication service returned {response.status_code}.",
            )
        return uuid.UUID(response.json()["id"])

    def delete_user(self, user_id: uuid.UUID) -> None:
        """Deletes the auth account; the database cascades to the profile."""
        try:
            response = httpx.delete(
                f"{self._url}/{user_id}", headers=self._headers, timeout=30
            )
        except httpx.HTTPError as exc:
            raise ApiError(
                503, "auth_unavailable", "The authentication service is unreachable."
            ) from exc
        # 404: the account is already gone, which is what was asked.
        if response.status_code >= 400 and response.status_code != 404:
            raise ApiError(
                503,
                "auth_unavailable",
                f"Authentication service returned {response.status_code}.",
            )


@lru_cache
def _default_auth_admin() -> SupabaseAuthAdmin:
    return SupabaseAuthAdmin(get_settings())


def get_auth_admin() -> AuthAdminClient:
    return _default_auth_admin()
