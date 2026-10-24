from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

SessionFactory = Callable[[], Session]


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _default_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session_factory() -> SessionFactory:
    """Factory for sessions outside the request (background processing, allowance).

    Overridden in tests so background work sees the test transaction.
    """
    return _default_session_factory()


def get_session(
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# scope="function" commits before the response is sent, not after.
DbSession = Annotated[Session, Depends(get_session, scope="function")]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]


def database_is_reachable() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("select 1"))
        return True
    except Exception:
        return False
