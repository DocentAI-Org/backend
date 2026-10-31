import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import jwt
import pytest

TEST_JWT_SECRET = "test-jwt-secret-with-at-least-32-characters"
os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
os.environ["LOG_PSEUDONYM_SECRET"] = "test-pseudonym-secret"
os.environ["DAILY_MESSAGE_LIMIT"] = "5"
# The app must not touch rows of a dev server sharing the local database.
os.environ["RECOVER_INTERRUPTED_ON_STARTUP"] = "false"
os.environ["RETRIEVAL_MIN_SIMILARITY"] = "0.2"
os.environ["RETRIEVAL_MIN_SIMILARITY_EXERCISES"] = "0.2"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.integrations.auth_admin import get_auth_admin  # noqa: E402
from app.integrations.storage import get_storage  # noqa: E402
from app.llm.client import get_llm  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Profile  # noqa: E402
from tests.fakes import (  # noqa: E402
    FakeAuthAdmin,
    FakeLLM,
    FakeStorage,
    insert_auth_user,
)

get_settings.cache_clear()
FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if f"{os.sep}api{os.sep}" in str(item.path):
            item.add_marker(pytest.mark.db)


def make_token(user_id: uuid.UUID, expires_in: int = 3600) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1 from public.profiles limit 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.exit(
            "Local Supabase database is not reachable or not migrated "
            f"({exc.__class__.__name__}). Run `npx supabase start` (or `db start`).",
            returncode=1,
        )
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine) -> Iterator[sessionmaker[Session]]:
    """All sessions of a test share one connection, rolled back at the end."""
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield factory
    transaction.rollback()
    connection.close()


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def auth_admin(session_factory) -> FakeAuthAdmin:
    return FakeAuthAdmin(session_factory)


@pytest.fixture
def client(session_factory, llm, storage, auth_admin) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_auth_admin] = lambda: auth_admin
    with TestClient(app) as test_client:
        yield test_client


@dataclass
class User:
    id: uuid.UUID
    role: str
    display_name: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def make_user(db):
    def factory(role: str = "student", display_name: str | None = None) -> User:
        name = display_name or f"{role.title()} {uuid.uuid4().hex[:6]}"
        user_id = insert_auth_user(db, f"{uuid.uuid4().hex[:10]}@example.org", name)
        db.flush()
        profile = db.get(Profile, user_id)
        assert profile is not None
        profile.role = role
        db.commit()
        return User(user_id, role, name, make_token(user_id))

    return factory


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "Admin")


@pytest.fixture
def teacher(make_user) -> User:
    return make_user("teacher", "Prof. Elena Ruiz")


@pytest.fixture
def other_teacher(make_user) -> User:
    return make_user("teacher", "Prof. Otro")


@pytest.fixture
def student(make_user) -> User:
    return make_user("student", "Lucas Herrera")


@pytest.fixture
def other_student(make_user) -> User:
    return make_user("student", "Estudiante-07")
