"""Supabase JWT verification and role dependencies (AGENTS.md II, research R8)."""

import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.db import DbSession
from app.core.errors import forbidden, unauthenticated
from app.models import Profile

bearer_scheme = HTTPBearer(auto_error=False, description="Supabase Auth access token")


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def verify_token(token: str, settings: Settings) -> uuid.UUID:
    """Returns the auth user id (`sub`) of a valid Supabase access token."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            if not settings.supabase_jwt_secret:
                raise unauthenticated()
            key: str | jwt.PyJWK = settings.supabase_jwt_secret
            algorithms = ["HS256"]
        else:
            jwks_url = (
                f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            )
            key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
            algorithms = ["ES256", "RS256", "EdDSA"]
        claims = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=settings.jwt_audience,
            options={"require": ["exp", "sub"]},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise unauthenticated() from exc


def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Profile:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthenticated()
    user_id = verify_token(credentials.credentials, get_settings())
    profile = session.get(Profile, user_id)
    if profile is None:
        raise unauthenticated()
    if profile.status != "active":
        raise forbidden("This account is disabled.")
    return profile


CurrentUser = Annotated[Profile, Depends(get_current_user)]


def require_role(role: str) -> Callable[[Profile], Profile]:
    def dependency(user: CurrentUser) -> Profile:
        if user.role != role:
            raise forbidden()
        return user

    return dependency


AdminUser = Annotated[Profile, Depends(require_role("admin"))]
TeacherUser = Annotated[Profile, Depends(require_role("teacher"))]
StudentUser = Annotated[Profile, Depends(require_role("student"))]
