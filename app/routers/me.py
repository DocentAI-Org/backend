from fastapi import APIRouter

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import CurrentUser
from app.schemas.me import Me, MeUpdate

router = APIRouter(prefix="/me", tags=["me"], responses=error_responses(401, 403))


@router.get("", response_model=Me)
def read_me(user: CurrentUser) -> Me:
    return Me.from_profile(user)


@router.patch("", response_model=Me, responses=error_responses(422))
def update_me(payload: MeUpdate, user: CurrentUser, session: DbSession) -> Me:
    user.preferred_language = payload.preferred_language
    session.flush()
    return Me.from_profile(user)
