"""Pre-test and post-test (P3, specs/008): one test per course, taken once per phase.

The questions are frozen once the pre-test has been opened, so both phases measure the
same thing. Students never see right or wrong: it would teach the post-test.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.models import (
    Course,
    Enrolment,
    QuizQuestion,
    TestAnswer,
    TestAttempt,
    TestPhase,
    TestQuestion,
    Topic,
)
from app.schemas import course_tests as schemas
from app.services import consent

PHASES = ("pre", "post")


# --- Shared ------------------------------------------------------------------------


def _questions(session: Session, course_id: uuid.UUID) -> list[TestQuestion]:
    return list(
        session.scalars(
            select(TestQuestion)
            .where(TestQuestion.course_id == course_id)
            .order_by(TestQuestion.position, TestQuestion.created_at)
        )
    )


def _phase(session: Session, course_id: uuid.UUID, phase: str) -> TestPhase:
    row = session.get(TestPhase, (course_id, phase))
    if row is None:
        row = TestPhase(course_id=course_id, phase=phase, status="not_open")
        session.add(row)
        session.flush()
    return row


def _locked(session: Session, course_id: uuid.UUID) -> bool:
    pre = session.get(TestPhase, (course_id, "pre"))
    return pre is not None and pre.opened_at is not None


def _submitted(session: Session, course_id: uuid.UUID) -> dict[str, int]:
    rows = session.execute(
        select(TestAttempt.phase, func.count())
        .where(TestAttempt.course_id == course_id)
        .group_by(TestAttempt.phase)
    ).all()
    return dict(rows)  # type: ignore[arg-type]


def _phase_views(session: Session, course_id: uuid.UUID) -> list[schemas.TestPhaseView]:
    counts = _submitted(session, course_id)
    views = []
    for phase in PHASES:
        row = session.get(TestPhase, (course_id, phase))
        views.append(
            schemas.TestPhaseView(
                phase=phase,  # type: ignore[arg-type]
                status=row.status if row else "not_open",  # type: ignore[arg-type]
                opened_at=row.opened_at if row else None,
                closed_at=row.closed_at if row else None,
                submitted_count=counts.get(phase, 0),
            )
        )
    return views


def question_view(question: TestQuestion) -> schemas.TestQuestion:
    return schemas.TestQuestion(
        id=question.id,
        topic_id=question.topic_id,
        topic_name=question.topic_name,
        position=question.position,
        statement=question.statement,
        options=list(question.options),
        correct_option=question.correct_option,
    )


# --- Teacher: questions ------------------------------------------------------------


def course_test(session: Session, course: Course) -> schemas.CourseTest:
    return schemas.CourseTest(
        locked=_locked(session, course.id),
        questions=[question_view(q) for q in _questions(session, course.id)],
        phases=_phase_views(session, course.id),
    )


def _ensure_unlocked(session: Session, course: Course) -> None:
    if _locked(session, course.id):
        raise ApiError(
            409,
            "test_locked",
            "The pre-test has been opened: the questions can no longer change.",
        )


def _topic(session: Session, course: Course, topic_id: uuid.UUID) -> Topic:
    topic = session.get(Topic, topic_id)
    if topic is None or topic.course_id != course.id:
        raise ApiError(
            422,
            "validation_error",
            "The topic is not in this course.",
            {"fields": {"topic_id": "unknown"}},
        )
    return topic


def _next_position(session: Session, course: Course) -> int:
    current = session.scalar(
        select(func.max(TestQuestion.position)).where(
            TestQuestion.course_id == course.id
        )
    )
    return (current or 0) + 1


def add_question(
    session: Session, course: Course, payload: schemas.TestQuestionCreate
) -> schemas.TestQuestion:
    _ensure_unlocked(session, course)
    topic = _topic(session, course, payload.topic_id)
    question = TestQuestion(
        course_id=course.id,
        topic_id=topic.id,
        topic_name=topic.name,
        position=_next_position(session, course),
        statement=payload.statement,
        options=payload.options,
        correct_option=payload.correct_option,
    )
    session.add(question)
    session.flush()
    return question_view(question)


def copy_quiz_question(
    session: Session, course: Course, question_id: uuid.UUID
) -> schemas.TestQuestion:
    _ensure_unlocked(session, course)
    source = session.get(QuizQuestion, question_id)
    if source is None or source.course_id != course.id or source.status != "approved":
        raise not_found("Question")
    question = TestQuestion(
        course_id=course.id,
        topic_id=source.topic_id,
        topic_name=source.topic.name,
        position=_next_position(session, course),
        statement=source.statement,
        options=list(source.options),
        correct_option=source.correct_option,
    )
    session.add(question)
    session.flush()
    return question_view(question)


def get_question(
    session: Session, course: Course, question_id: uuid.UUID
) -> TestQuestion:
    question = session.get(TestQuestion, question_id)
    if question is None or question.course_id != course.id:
        raise not_found("Question")
    return question


def update_question(
    session: Session,
    course: Course,
    question: TestQuestion,
    payload: schemas.TestQuestionUpdate,
) -> schemas.TestQuestion:
    _ensure_unlocked(session, course)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "topic_id" in changes:
        topic = _topic(session, course, changes.pop("topic_id"))
        question.topic_id, question.topic_name = topic.id, topic.name
    for field, value in changes.items():
        setattr(question, field, value)
    session.flush()
    return question_view(question)


def delete_question(session: Session, course: Course, question: TestQuestion) -> None:
    _ensure_unlocked(session, course)
    session.delete(question)
    session.flush()


# --- Teacher: phases and results ---------------------------------------------------


def set_phase(
    session: Session, course: Course, phase: str, status: str
) -> schemas.TestPhaseView:
    row = _phase(session, course.id, phase)
    now = datetime.now(UTC)
    if status == "open":
        if not _questions(session, course.id):
            raise ApiError(409, "test_empty", "Add questions before opening the test.")
        row.status, row.opened_at, row.closed_at = "open", row.opened_at or now, None
    else:
        row.status, row.closed_at = "closed", now
    session.flush()
    return next(v for v in _phase_views(session, course.id) if v.phase == phase)


def _score(
    attempt: TestAttempt, questions: dict[uuid.UUID, TestQuestion]
) -> schemas.PhaseScore:
    by_topic: dict[tuple[uuid.UUID | None, str], list[int]] = {}
    # Topics in the order of the test.
    for q in sorted(questions.values(), key=lambda q: q.position):
        by_topic.setdefault((q.topic_id, q.topic_name), [0, 0])
    for answer in attempt.answers:
        q = questions.get(answer.question_id)
        if q is None:
            continue
        score = by_topic[(q.topic_id, q.topic_name)]
        score[0] += int(answer.correct)
        score[1] += 1
    scores = [
        schemas.TestTopicScore(topic_id=tid, topic_name=name, right=r, total=t)
        for (tid, name), (r, t) in by_topic.items()
        if t
    ]
    return schemas.PhaseScore(
        submitted_at=attempt.submitted_at,
        right=sum(s.right for s in scores),
        total=sum(s.total for s in scores),
        by_topic=scores,
    )


def results(session: Session, course: Course) -> schemas.TestResults:
    questions = {q.id: q for q in _questions(session, course.id)}
    attempts = session.scalars(
        select(TestAttempt).where(TestAttempt.course_id == course.id)
    ).all()
    by_student: dict[uuid.UUID, dict[str, schemas.PhaseScore]] = defaultdict(dict)
    for attempt in attempts:
        by_student[attempt.student_id][attempt.phase] = _score(attempt, questions)

    enrolments = session.scalars(
        select(Enrolment).where(
            Enrolment.course_id == course.id, Enrolment.status == "active"
        )
    ).all()
    students = sorted(
        (
            schemas.StudentResult(
                student_id=e.student_id,
                display_name=e.student.display_name,
                pre=by_student[e.student_id].get("pre"),
                post=by_student[e.student_id].get("post"),
            )
            for e in enrolments
        ),
        key=lambda s: s.display_name.casefold(),
    )

    averages = []
    for phase in PHASES:
        scores = [s[phase] for s in by_student.values() if phase in s]
        topics: dict[tuple[uuid.UUID | None, str], list[float]] = {}
        for score in scores:
            for t in score.by_topic:
                topics.setdefault((t.topic_id, t.topic_name), []).append(
                    t.right / t.total
                )
        averages.append(
            schemas.PhaseAverage(
                phase=phase,  # type: ignore[arg-type]
                submitted=len(scores),
                score=sum(s.right / s.total for s in scores) / len(scores)
                if scores
                else None,
                by_topic=[
                    schemas.TopicAverage(
                        topic_id=tid, topic_name=name, score=sum(v) / len(v)
                    )
                    for (tid, name), v in topics.items()
                ],
            )
        )
    return schemas.TestResults(
        question_count=len(questions),
        phases=_phase_views(session, course.id),
        students=students,
        averages=averages,
    )


# --- Student -------------------------------------------------------------------------


def _attempt(session: Session, enrolment: Enrolment, phase: str) -> TestAttempt | None:
    return session.scalar(
        select(TestAttempt).where(
            TestAttempt.course_id == enrolment.course_id,
            TestAttempt.student_id == enrolment.student_id,
            TestAttempt.phase == phase,
        )
    )


def _status(session: Session, course_id: uuid.UUID, phase: str) -> str:
    row = session.get(TestPhase, (course_id, phase))
    return row.status if row else "not_open"


def student_phases(
    session: Session, enrolment: Enrolment
) -> list[schemas.StudentTestPhase]:
    count = len(_questions(session, enrolment.course_id))
    return [
        schemas.StudentTestPhase(
            phase=phase,  # type: ignore[arg-type]
            status=_status(session, enrolment.course_id, phase),  # type: ignore[arg-type]
            done=_attempt(session, enrolment, phase) is not None,
            question_count=count,
        )
        for phase in PHASES
    ]


def _not_open() -> ApiError:
    return ApiError(409, "test_not_open", "This test is not open.")


def student_test(
    session: Session, enrolment: Enrolment, phase: str
) -> schemas.StudentTest:
    status = _status(session, enrolment.course_id, phase)
    attempt = _attempt(session, enrolment, phase)
    if attempt is None and status != "open":
        raise _not_open()
    return schemas.StudentTest(
        phase=phase,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        done=attempt is not None,
        submitted_at=attempt.submitted_at if attempt else None,
        questions=[]
        if attempt
        else [
            schemas.StudentTestQuestion(
                id=q.id,
                position=q.position,
                statement=q.statement,
                options=list(q.options),
                topic_name=q.topic_name,
            )
            for q in _questions(session, enrolment.course_id)
        ],
    )


def submit(
    session: Session,
    settings: Settings,
    enrolment: Enrolment,
    phase: str,
    payload: schemas.TestSubmission,
) -> schemas.TestSubmitted:
    consent.require(session, settings, enrolment.student_id)
    if _attempt(session, enrolment, phase) is not None:
        raise ApiError(409, "test_already_done", "This test has already been taken.")
    if _status(session, enrolment.course_id, phase) != "open":
        raise _not_open()
    questions = {q.id: q for q in _questions(session, enrolment.course_id)}
    given = [a.question_id for a in payload.answers]
    if len(given) != len(set(given)) or set(given) != set(questions):
        raise ApiError(
            422,
            "validation_error",
            "Answer every question of the test exactly once.",
            {"fields": {"answers": "incomplete"}},
        )
    attempt = TestAttempt(
        course_id=enrolment.course_id, student_id=enrolment.student_id, phase=phase
    )
    session.add(attempt)
    session.flush()
    session.add_all(
        TestAnswer(
            attempt_id=attempt.id,
            question_id=a.question_id,
            choice=a.choice,
            correct=a.choice == questions[a.question_id].correct_option,
        )
        for a in payload.answers
    )
    session.flush()
    session.refresh(attempt)
    return schemas.TestSubmitted(
        phase=phase,  # type: ignore[arg-type]
        submitted_at=attempt.submitted_at,
    )
