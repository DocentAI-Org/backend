"""Teacher routes: every endpoint is limited to courses the teacher owns."""

from fastapi import APIRouter, Depends

from app.core.errors import error_responses
from app.core.security import require_role
from app.routers.teacher import (
    course_tests,
    courses,
    dashboard,
    documents,
    pedagogy,
    quizzes,
    review,
    settings,
    topics,
)

router = APIRouter(
    prefix="/teacher",
    dependencies=[Depends(require_role("teacher"))],
    responses=error_responses(401, 403),
)
router.include_router(courses.router)
router.include_router(documents.router)
router.include_router(settings.router)
router.include_router(topics.router)
router.include_router(review.router)
router.include_router(dashboard.router)
router.include_router(quizzes.router)
router.include_router(course_tests.router)
router.include_router(pedagogy.router)
