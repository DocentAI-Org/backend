import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.errors import error_responses
from app.core.security import TeacherUser
from app.schemas.dashboard import (
    Period,
    RiskCriteriaList,
    RiskCriterionView,
    StudentRisk,
    TeacherDashboard,
)
from app.schemas.next_steps import NextSteps
from app.schemas.progress import Progress
from app.services import courses, dashboard, next_steps, progress, risk

router = APIRouter(tags=["teacher: dashboard"])


@router.get(
    "/courses/{course_id}/dashboard",
    response_model=TeacherDashboard,
    responses=error_responses(404, 422),
    summary="Recurring errors by topic and by student, and at-risk students",
)
def read_dashboard(
    course_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
    period: Annotated[Period, Query()] = "30d",
) -> TeacherDashboard:
    course = courses.get_owned_course(session, course_id, teacher)
    return dashboard.course_dashboard(session, course, period)


@router.get(
    "/courses/{course_id}/students/{student_id}/risk",
    response_model=StudentRisk,
    responses=error_responses(404),
    summary="Whether a student is at risk, why, and their weekly activity",
)
def read_student_risk(
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> StudentRisk:
    course = courses.get_owned_course(session, course_id, teacher)
    enrolment = courses.get_course_enrolment(session, course, student_id)
    return dashboard.student_risk(session, course, enrolment)


@router.get(
    "/courses/{course_id}/students/{student_id}/progress",
    response_model=Progress,
    responses=error_responses(404),
    summary="A student's progress and mastery by topic",
    description="Exactly what the student sees in their own progress (spec 007).",
)
def read_student_progress(
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> Progress:
    course = courses.get_owned_course(session, course_id, teacher)
    enrolment = courses.get_course_enrolment(session, course, student_id)
    return progress.student_progress(
        session, get_settings(), course.id, enrolment.student_id
    )


@router.get(
    "/courses/{course_id}/students/{student_id}/next-steps",
    response_model=NextSteps,
    responses=error_responses(404),
    summary="A student's recommended next steps",
    description="Exactly what the student sees as their next steps (spec 020).",
)
def read_student_next_steps(
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    teacher: TeacherUser,
    session: DbSession,
) -> NextSteps:
    course = courses.get_owned_course(session, course_id, teacher)
    enrolment = courses.get_course_enrolment(session, course, student_id)
    return next_steps.next_steps(session, get_settings(), enrolment)


@router.get(
    "/risk-criteria",
    response_model=RiskCriteriaList,
    summary="The criteria that flag a student as at risk",
)
def list_risk_criteria(_: TeacherUser, session: DbSession) -> RiskCriteriaList:
    criteria, provisional = risk.study_criteria(session)
    return RiskCriteriaList(
        provisional=provisional,
        items=[
            RiskCriterionView(code=c.code, enabled=c.enabled, thresholds=c.thresholds)
            for c in criteria
        ],
    )
