from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.db import database_is_reachable
from app.llm.client import LLMClient, get_llm
from app.schemas.me import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health_check(llm: Annotated[LLMClient, Depends(get_llm)]) -> Health:
    settings = get_settings()
    database = "ok" if database_is_reachable() else "error"
    model = "ok" if llm.is_reachable() else "error"
    return Health(
        status="ok" if database == "ok" and model == "ok" else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        database=database,
        llm=model,
    )
