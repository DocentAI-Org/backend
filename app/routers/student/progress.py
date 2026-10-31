import uuid

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import StudentUser
from app.schemas.progress import Progress
from app.services import courses, progress

router = APIRouter(prefix="/courses/{course_id}", tags=["student: progress"])


@router.get(
    "/progress",
    response_model=Progress,
    responses=error_responses(403, 404),
    summary="My progress and mastery by topic",
    description=(
        "Every course topic with a provisional mastery level, its score and the graded "
        "exercises and quiz answers behind it, a weekly history and the most frequent "
        "mistakes. The teacher sees exactly the same (spec 007)."
    ),
)
def read_progress(
    course_id: uuid.UUID, student: StudentUser, session: DbSession
) -> Progress:
    enrolment = courses.get_active_enrolment(session, course_id, student)
    return progress.student_progress(
        session, get_settings(), enrolment.course_id, student.id
    )
