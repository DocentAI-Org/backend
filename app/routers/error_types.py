from fastapi import APIRouter
from sqlalchemy import select

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import CurrentUser
from app.models import ErrorType
from app.schemas.exercises import ErrorTaxonomy, ErrorTypeView, Localized

router = APIRouter(
    prefix="/error-types", tags=["exercises"], responses=error_responses(401, 403)
)


@router.get(
    "",
    response_model=ErrorTaxonomy,
    summary="The error taxonomy used to classify exercise mistakes",
)
def list_error_types(_: CurrentUser, session: DbSession) -> ErrorTaxonomy:
    types = session.scalars(select(ErrorType).order_by(ErrorType.position)).all()
    return ErrorTaxonomy(
        provisional=any(t.provisional for t in types),
        items=[
            ErrorTypeView(
                code=t.code,
                label=Localized(es=t.label_es, en=t.label_en),
                description=Localized(es=t.description_es, en=t.description_en),
            )
            for t in types
        ],
    )
