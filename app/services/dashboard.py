"""Teacher dashboard (specs/004): recurring errors and at-risk students."""

import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Conversation,
    Course,
    Enrolment,
    ErrorType,
    ExerciseSubmission,
    LearningRecordEntry,
    Message,
    Quiz,
    Topic,
)
from app.schemas.dashboard import (
    ActivityCounts,
    AtRiskStudent,
    Period,
    StudentErrors,
    StudentRisk,
    TeacherDashboard,
    TopicErrors,
    WeekActivity,
)
from app.services import risk

PERIOD_DAYS = {"7d": 7, "30d": 30, "all": None}
# Prototype F12: "at least 20 messages or 5 exercises".
ENOUGH_DATA = ActivityCounts(messages=20, exercises=5)
MISTAKES = ("incorrect", "partially_correct")
WEEKS = 8


def active_students(
    session: Session, course: Course, student_id: uuid.UUID | None = None
) -> list[Enrolment]:
    query = select(Enrolment).where(
        Enrolment.course_id == course.id, Enrolment.status == "active"
    )
    if student_id is not None:
        query = query.where(Enrolment.student_id == student_id)
    return list(session.scalars(query))


def student_messages(course: Course, ids: list[uuid.UUID]):
    return (
        select(Conversation.student_id, Message.created_at)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.course_id == course.id,
            Conversation.student_id.in_(ids),
            Message.author == "student",
            Message.status == "sent",
        )
    )


def submissions(course: Course, ids: list[uuid.UUID]):
    return select(ExerciseSubmission.student_id, ExerciseSubmission.created_at).where(
        ExerciseSubmission.course_id == course.id,
        ExerciseSubmission.student_id.in_(ids),
    )


def count_since(session: Session, query, since: datetime | None) -> int:
    subquery = query.subquery()
    count = select(func.count()).select_from(subquery)
    if since is not None:
        count = count.where(subquery.c.created_at >= since)
    return session.scalar(count) or 0


def last_activity(
    session: Session, course: Course, ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    union = student_messages(course, ids).union_all(submissions(course, ids)).subquery()
    rows = session.execute(
        select(union.c.student_id, func.max(union.c.created_at)).group_by(
            union.c.student_id
        )
    )
    return dict(rows.all())


def exercise_outcomes(
    session: Session, course: Course, ids: list[uuid.UUID], since: datetime
) -> dict[uuid.UUID, tuple[int, int]]:
    """(assessed, mistakes) per student since a date, without stubs or not_assessed."""
    rows = session.execute(
        select(
            ExerciseSubmission.student_id,
            func.count(),
            func.count().filter(ExerciseSubmission.verdict.in_(MISTAKES)),
        )
        .where(
            ExerciseSubmission.course_id == course.id,
            ExerciseSubmission.student_id.in_(ids),
            ExerciseSubmission.verdict != "not_assessed",
            ExerciseSubmission.is_stub.is_(False),
            ExerciseSubmission.created_at >= since,
        )
        .group_by(ExerciseSubmission.student_id)
    )
    return {student: (assessed, mistakes) for student, assessed, mistakes in rows}


def risk_reasons(
    session: Session,
    course: Course,
    enrolments: list[Enrolment],
    criteria: list[risk.Criterion],
    now: datetime,
) -> tuple[dict[uuid.UUID, list], dict[uuid.UUID, datetime]]:
    ids = [e.student_id for e in enrolments]
    last = last_activity(session, course, ids) if ids else {}
    outcomes: dict[uuid.UUID, tuple[int, int]] = {}
    error_rate = risk.enabled(criteria, "error_rate")
    if error_rate and ids:
        window = now - timedelta(days=error_rate.thresholds["window_days"])
        outcomes = exercise_outcomes(session, course, ids, window)
    reasons = {}
    for e in enrolments:
        assessed, mistakes = outcomes.get(e.student_id, (0, 0))
        facts = risk.StudentFacts(
            joined_at=e.joined_at,
            last_activity_at=last.get(e.student_id),
            assessed=assessed,
            mistakes=mistakes,
        )
        reasons[e.student_id] = risk.evaluate(criteria, facts, now)
    return reasons, last


def top(counter: Counter, rank) -> str | None:
    """The most frequent key; ties go to the lowest `rank(key)`."""
    if not counter:
        return None
    return min(counter, key=lambda key: (-counter[key], rank(key)))


def errors(
    session: Session,
    course: Course,
    enrolments: list[Enrolment],
    since: datetime | None,
) -> tuple[list[TopicErrors], list[StudentErrors]]:
    positions = dict(session.execute(select(ErrorType.code, ErrorType.position)).all())
    names = {e.student_id: e.student.display_name for e in enrolments}
    topic_name = func.coalesce(Topic.name, LearningRecordEntry.topic_name)
    query = (
        select(
            LearningRecordEntry.student_id,
            LearningRecordEntry.topic_id,
            topic_name,
            LearningRecordEntry.error_type,
            func.count(),
        )
        .outerjoin(Topic, Topic.id == LearningRecordEntry.topic_id)
        .where(
            LearningRecordEntry.course_id == course.id,
            LearningRecordEntry.student_id.in_(list(names)),
            LearningRecordEntry.error_type.in_(list(positions)),
        )
        .group_by(
            LearningRecordEntry.student_id,
            LearningRecordEntry.topic_id,
            topic_name,
            LearningRecordEntry.error_type,
        )
    )
    if since is not None:
        query = query.where(LearningRecordEntry.created_at >= since)

    by_topic: dict[tuple, Counter] = defaultdict(Counter)
    topic_students: dict[tuple, set] = defaultdict(set)
    by_student: dict[uuid.UUID, Counter] = defaultdict(Counter)
    student_topics: dict[uuid.UUID, Counter] = defaultdict(Counter)
    for student_id, topic_id, name, error_type, count in session.execute(query):
        key = (topic_id, name)
        by_topic[key][error_type] += count
        topic_students[key].add(student_id)
        by_student[student_id][error_type] += count
        student_topics[student_id][name] += count

    def rank(code: str) -> int:
        return positions[code]

    topics = [
        TopicErrors(
            topic_id=topic_id,
            topic_name=name,
            topic_deleted=topic_id is None and name is not None,
            errors=sum(counter.values()),
            students=len(topic_students[(topic_id, name)]),
            # Every counter has at least one error, so there is a top type.
            top_error_type=cast(str, top(counter, rank)),
        )
        for (topic_id, name), counter in by_topic.items()
    ]
    topics.sort(key=lambda t: (-t.errors, t.topic_name is None, t.topic_name or ""))
    students = [
        StudentErrors(
            student_id=student_id,
            display_name=names[student_id],
            errors=sum(counter.values()),
            # Every counter has at least one error, so there is a top type.
            top_error_type=cast(str, top(counter, rank)),
            top_topic_name=top(
                student_topics[student_id], lambda n: (n is None, n or "")
            ),
        )
        for student_id, counter in by_student.items()
    ]
    students.sort(key=lambda s: (-s.errors, s.display_name))
    return topics, students


def course_dashboard(
    session: Session, course: Course, period: Period, now: datetime | None = None
) -> TeacherDashboard:
    now = now or datetime.now(UTC)
    days = PERIOD_DAYS[period]
    since = now - timedelta(days=days) if days else None
    enrolments = active_students(session, course)
    ids = [e.student_id for e in enrolments]
    criteria, provisional = risk.criteria_for(session, course)

    activity = ActivityCounts(
        messages=count_since(session, student_messages(course, ids), since),
        exercises=count_since(session, submissions(course, ids), since),
    )
    topics, students = errors(session, course, enrolments, since)
    reasons, last = risk_reasons(session, course, enrolments, criteria, now)
    at_risk = [
        AtRiskStudent(
            student_id=e.student_id,
            display_name=e.student.display_name,
            last_activity_at=last.get(e.student_id),
            reasons=reasons[e.student_id],
        )
        for e in sorted(enrolments, key=lambda e: e.student.display_name)
        if reasons[e.student_id]
    ]
    return TeacherDashboard(
        period=period,
        since=since,
        activity=activity,
        enough_data=activity.messages >= ENOUGH_DATA.messages
        or activity.exercises >= ENOUGH_DATA.exercises,
        thresholds=ENOUGH_DATA,
        errors_by_topic=topics,
        errors_by_student=students,
        at_risk=at_risk,
        criteria_provisional=provisional,
    )


def weekly_activity(
    session: Session, course: Course, student_id: uuid.UUID, now: datetime
) -> list[WeekActivity]:
    today = now.date()
    this_week = today - timedelta(days=today.weekday())
    weeks = [this_week - timedelta(weeks=i) for i in range(WEEKS - 1, -1, -1)]
    start = datetime.combine(weeks[0], datetime.min.time(), tzinfo=UTC)
    counts: dict[date, Counter] = {week: Counter() for week in weeks}
    for kind, query in (
        ("messages", student_messages(course, [student_id])),
        ("exercises", submissions(course, [student_id])),
    ):
        subquery = query.subquery()
        for (created_at,) in session.execute(
            select(subquery.c.created_at).where(subquery.c.created_at >= start)
        ):
            day = created_at.astimezone(UTC).date()
            counts[day - timedelta(days=day.weekday())][kind] += 1
    for (completed_at,) in session.execute(
        select(Quiz.completed_at).where(
            Quiz.course_id == course.id,
            Quiz.student_id == student_id,
            Quiz.completed_at >= start,
        )
    ):
        assert completed_at is not None  # filtered by the query
        day = completed_at.astimezone(UTC).date()
        counts[day - timedelta(days=day.weekday())]["quizzes"] += 1
    return [
        WeekActivity(
            week_start=week,
            messages=counts[week]["messages"],
            exercises=counts[week]["exercises"],
            quizzes=counts[week]["quizzes"],
        )
        for week in weeks
    ]


def student_risk(
    session: Session, course: Course, enrolment: Enrolment, now: datetime | None = None
) -> StudentRisk:
    """A revoked student is never at risk; their activity is still shown."""
    now = now or datetime.now(UTC)
    criteria, provisional = risk.criteria_for(session, course)
    reasons: list = []
    if enrolment.status == "active":
        by_student, last = risk_reasons(session, course, [enrolment], criteria, now)
        reasons = by_student[enrolment.student_id]
    else:
        last = last_activity(session, course, [enrolment.student_id])
    return StudentRisk(
        student_id=enrolment.student_id,
        display_name=enrolment.student.display_name,
        at_risk=bool(reasons),
        reasons=reasons,
        last_activity_at=last.get(enrolment.student_id),
        weekly_activity=weekly_activity(session, course, enrolment.student_id, now),
        criteria_provisional=provisional,
    )
