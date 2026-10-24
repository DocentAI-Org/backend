import uuid

from fastapi import APIRouter

from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import TeacherUser
from app.models import TutorSettings as TutorSettingsRow
from app.schemas.tutor import TutorSettings, TutorSettingsUpdate
from app.services import courses

router = APIRouter(prefix="/courses/{course_id}", tags=["teacher: tutor settings"])


def _view(row: TutorSettingsRow) -> TutorSettings:
    return TutorSettings.model_validate(row, from_attributes=True)


@router.get(
    "/tutor-settings", response_model=TutorSettings, responses=error_responses(404)
)
def read_settings(
    course_id: uuid.UUID, teacher: TeacherUser, session: DbSession
) -> TutorSettings:
    course = courses.get_owned_course(session, course_id, teacher)
    row = session.get(TutorSettingsRow, course.id)
    assert row is not None
    return _view(row)


@router.put(
    "/tutor-settings",
    response_model=TutorSettings,
    responses=error_responses(404, 422),
)
def update_settings(
    course_id: uuid.UUID,
    payload: TutorSettingsUpdate,
    teacher: TeacherUser,
    session: DbSession,
) -> TutorSettings:
    course = courses.get_owned_course(session, course_id, teacher)
    row = session.get(TutorSettingsRow, course.id)
    assert row is not None
    row.level = payload.level
    row.tone = payload.tone
    row.solution_policy = payload.solution_policy
    session.flush()
    session.refresh(row)
    return _view(row)
