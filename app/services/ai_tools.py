"""Tools around a course's AI settings (specs/019): a test message with unsaved
settings, and the course's usage."""

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.llm.catalog import Catalog
from app.llm.client import ChatResult, LLMClient, LLMError
from app.models import (
    AITest,
    Course,
    CourseUsage,
    Enrolment,
    ErrorType,
    InteractionLog,
    Profile,
    Topic,
    TutorSettings,
)
from app.schemas import ai_settings as schemas
from app.services import ai_settings, allowance, exercises, interactions, tutor
from app.services.ai_settings import TASKS, InEffect
from app.services.retrieval import retrieve

TESTS_PER_HOUR = 20
# What each logged interaction was for; student quizzes call no model.
TASK_OF_KIND = {
    "chat": "tutor",
    "exercise": "feedback",
    "review": "review",
    "quiz_generation": "questions",
}


def _take_test(session: Session, course: Course, teacher: Profile, task: str) -> None:
    since = datetime.now(UTC) - timedelta(hours=1)
    done = session.scalar(
        select(func.count())
        .select_from(AITest)
        .where(AITest.teacher_id == teacher.id, AITest.created_at > since)
    )
    if (done or 0) >= TESTS_PER_HOUR:
        raise ApiError(
            429,
            "test_limit_reached",
            f"At most {TESTS_PER_HOUR} test messages an hour.",
        )
    session.add(AITest(course_id=course.id, teacher_id=teacher.id, task=task))
    session.flush()


def _tutor(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    ai: InEffect,
    course: Course,
    tutor_settings: TutorSettings,
    message: str,
) -> tuple[str, str, int, ChatResult | None]:
    hits = retrieve(
        session,
        llm,
        course.id,
        message,
        ai.retrieval.top_k,
        ai.retrieval.min_similarity,
    )
    if not hits:
        return "no_source", tutor.no_source_text(settings), 0, None
    system = tutor.build_system_prompt(
        settings, tutor_settings, False, teacher=ai.instruction("tutor")
    )
    result = llm.chat_json(
        system,
        tutor.build_messages([], hits, message),
        task="tutor",
        route=ai.route("tutor"),
    )
    reply = tutor.ground_reply(result.data, len(hits))
    return reply.kind, reply.text or tutor.no_source_text(settings), len(hits), result


def _feedback(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    ai: InEffect,
    course: Course,
    tutor_settings: TutorSettings,
    problem: str,
    answer: str,
) -> tuple[str, str, int, ChatResult | None]:
    hits = retrieve(
        session,
        llm,
        course.id,
        f"{problem}\n{answer}",
        ai.retrieval.top_k,
        ai.retrieval.min_similarity_exercises,
    )
    if not hits:
        return "not_assessed", tutor.no_source_text(settings), 0, None
    topics = list(
        session.scalars(
            select(Topic).where(Topic.course_id == course.id).order_by(Topic.position)
        )
    )
    error_types = list(session.scalars(select(ErrorType).order_by(ErrorType.position)))
    result = llm.chat_json(
        exercises.build_feedback_prompt(
            settings, tutor_settings, teacher=ai.instruction("feedback")
        ),
        exercises.build_feedback_messages(
            hits,
            topics,
            error_types,
            problem,
            answer,
            exercises.fragment_topic_refs(session, hits, topics),
        ),
        temperature=settings.llm_feedback_temperature,
        task="feedback",
        route=ai.route("feedback"),
    )
    feedback = exercises.validate_feedback(
        result.data, len(hits), len(topics), {t.code for t in error_types}
    )
    if feedback is None:
        return "not_assessed", "", len(hits), result
    return feedback.verdict, feedback.explanation, len(hits), result


def test_message(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    catalog: Catalog,
    course: Course,
    teacher: Profile,
    payload: schemas.AITestRequest,
) -> schemas.AITestResult:
    """Runs the task as a student would, with the given settings; nothing is stored but
    the count of tests."""
    ai = (
        ai_settings.preview(session, settings, catalog, course, payload.settings)
        if payload.settings
        else ai_settings.in_effect(session, settings, course.id)
    )
    _take_test(session, course, teacher, payload.task)
    tutor_settings = session.get(TutorSettings, course.id)
    assert tutor_settings is not None
    started = time.perf_counter()
    try:
        if payload.task == "tutor":
            kind, text, fragments, result = _tutor(
                session,
                llm,
                settings,
                ai,
                course,
                tutor_settings,
                payload.message or "",
            )
        else:
            kind, text, fragments, result = _feedback(
                session,
                llm,
                settings,
                ai,
                course,
                tutor_settings,
                payload.problem_statement or "",
                payload.worked_answer or "",
            )
    except LLMError:
        raise ApiError(
            503, "tutor_unavailable", "The model could not answer the test."
        ) from None
    input_tokens = result.input_tokens if result else 0
    output_tokens = result.output_tokens if result else 0
    model = result.model if result else None
    return schemas.AITestResult(
        kind=kind,
        text=text,
        model=model,
        latency_ms=int((time.perf_counter() - started) * 1000),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=float(
            interactions.estimate_cost(settings, input_tokens, output_tokens, model)
        ),
        fragments=fragments,
    )


def _window(session: Session, course: Course, days: int) -> schemas.UsageWindow:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.execute(
        select(
            InteractionLog.kind,
            func.count(),
            func.coalesce(func.sum(InteractionLog.input_tokens), 0),
            func.coalesce(func.sum(InteractionLog.output_tokens), 0),
            func.coalesce(func.sum(InteractionLog.estimated_cost_usd), 0),
        )
        .where(
            InteractionLog.course_id == course.id,
            InteractionLog.created_at > since,
            InteractionLog.error_code.is_(None),
            InteractionLog.kind.in_(TASK_OF_KIND),
        )
        .group_by(InteractionLog.kind)
    ).all()
    found = {TASK_OF_KIND[kind]: row for kind, *row in rows}
    return schemas.UsageWindow(
        days=days,
        tasks=[
            schemas.TaskUsage(
                task=task,
                messages=int(found[task][0]) if task in found else 0,
                input_tokens=int(found[task][1]) if task in found else 0,
                output_tokens=int(found[task][2]) if task in found else 0,
                estimated_cost_usd=float(found[task][3]) if task in found else 0.0,
            )
            for task in TASKS
        ],
    )


def usage(session: Session, settings: Settings, course: Course) -> schemas.AIUsage:
    limits = ai_settings.in_effect(session, settings, course.id).limits
    top = session.execute(
        select(CourseUsage.student_id, Profile.display_name, CourseUsage.used)
        .join(Profile, Profile.id == CourseUsage.student_id)
        .join(
            Enrolment,
            (Enrolment.student_id == CourseUsage.student_id)
            & (Enrolment.course_id == course.id),
        )
        .where(
            CourseUsage.course_id == course.id,
            CourseUsage.period == limits.period,
            CourseUsage.period_start == allowance.period_start(settings, limits.period),
            CourseUsage.used > 0,
        )
        .order_by(CourseUsage.used.desc(), Profile.display_name)
        .limit(5)
    ).all()
    return schemas.AIUsage(
        windows=[_window(session, course, 7), _window(session, course, 30)],
        limit=limits.messages,
        period=limits.period,
        top_students=[
            schemas.StudentUsage(student_id=s, display_name=name, used=used)
            for s, name, used in top
        ],
    )
