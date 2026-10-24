import time
import uuid

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import verify_token

SECRET = "unit-test-secret-with-enough-length-123"


def _settings() -> Settings:
    return Settings(supabase_jwt_secret=SECRET)


def _token(**overrides: object) -> str:
    now = int(time.time())
    claims = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "exp": now + 60,
        **overrides,
    }
    return jwt.encode(claims, SECRET, algorithm="HS256")


def test_valid_hs256_token_returns_subject() -> None:
    user_id = uuid.uuid4()

    assert verify_token(_token(sub=str(user_id)), _settings()) == user_id


@pytest.mark.parametrize(
    "token",
    [
        _token(exp=int(time.time()) - 5),
        _token(aud="anon"),
        _token(sub="not-a-uuid"),
        jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated"}, SECRET, "HS256"),
        jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "aud": "authenticated",
                "exp": int(time.time()) + 60,
            },
            "another-secret-with-enough-length-12345",
            "HS256",
        ),
    ],
)
def test_invalid_tokens_are_rejected(token: str) -> None:
    with pytest.raises(ApiError) as error:
        verify_token(token, _settings())
    assert error.value.code == "unauthenticated"


def test_hs256_token_is_rejected_without_configured_secret() -> None:
    with pytest.raises(ApiError):
        verify_token(_token(), Settings(supabase_jwt_secret=None))
