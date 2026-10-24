import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.errors import register_error_handlers
from app.routers import admin, health, me, student, teacher
from app.services.documents import recover_interrupted

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Background processing does not survive a restart (research R10).
    if not get_settings().recover_interrupted_on_startup:
        yield
        return
    try:
        with get_session_factory()() as session:
            recovered = recover_interrupted(session)
        if recovered:
            logger.warning("Marked %d interrupted documents as failed", recovered)
    except Exception:
        logger.exception("Could not check for interrupted documents")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "DocentAI API v1. Errors use one schema with a stable `code`; "
            "endpoints marked `x-stub` honor the contract with fixed content."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    v1 = APIRouter(prefix="/v1")
    v1.include_router(health.router)
    v1.include_router(me.router)
    v1.include_router(admin.router)
    v1.include_router(teacher.router)
    v1.include_router(student.router)
    app.include_router(v1)
    return app


app = create_app()
