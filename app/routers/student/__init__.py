"""Student routes: own data in courses the student is actively enrolled in."""

from fastapi import APIRouter, Depends

from app.core.errors import error_responses
from app.core.security import require_role
from app.routers.student import (
    chat,
    consent,
    course_tests,
    courses,
    exercises,
    progress,
    quizzes,
)

router = APIRouter(
    prefix="/student",
    dependencies=[Depends(require_role("student"))],
    responses=error_responses(401, 403),
)
router.include_router(courses.router)
router.include_router(chat.router)
router.include_router(exercises.router)
router.include_router(quizzes.router)
router.include_router(progress.router)
router.include_router(course_tests.router)
router.include_router(consent.router)
