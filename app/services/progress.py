"""Progress and mastery by topic (S7, T8, specs/007), computed on read.

Provisional criteria (FR-001): the score of a topic is the share right among the latest
`window` graded items (an exercise counts 1, ½ or 0; a quiz answer 1 or 0).
"""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    ExerciseSubmission,
    LearningRecordEntry,
    Quiz,
    QuizItem,
    Topic,
)
from app.schemas import progress as schemas
from app.services import overcome, pedagogy

WEEKS = 8
EXERCISE_VALUE = {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0}
TOP_ERRORS = 3


@dataclass(frozen=True)
class Criteria:
    window: int
    min_items: int
    progressing: float
    mastered: float
    overcome_after: int = 3

    @classmethod
    def of_course(cls, session: Session, course_id: uuid.UUID) -> "Criteria":
        """The course's mastery criteria (its own or the study's, specs/015), and when a
        mistake is overcome (specs/022)."""
        criteria = pedagogy.in_effect(session, course_id).criteria
        mastery = criteria.mastery
        return cls(
            window=mastery.window,
            min_items=mastery.min_items,
            progressing=mastery.progressing,
            mastered=mastery.mastered,
            overcome_after=criteria.repeated_mistakes.overcome_after,
        )


@dataclass(frozen=True)
class Item:
    at: datetime
    value: float
    kind: str = "quiz"


def _latest(items: list[Item], criteria: Criteria) -> list[Item]:
    return sorted(items, key=lambda i: i.at)[-criteria.window :]


def score_of(items: list[Item], criteria: Criteria) -> float | None:
    """Mean of the latest `window` items; None with fewer than `min_items`."""
    latest = _latest(items, criteria)
    if len(latest) < criteria.min_items:
        return None
    return sum(i.value for i in latest) / len(latest)


def level_of(count: int, score: float | None, criteria: Criteria) -> str:
    if count == 0:
        return "not_started"
    if score is None:
        return "insufficient"
    if score >= criteria.mastered:
        return "mastered"
    if score >= criteria.progressing:
        return "progressing"
    return "starting"


def history_of(
    items: list[Item], weeks: list[date], criteria: Criteria
) -> list[float | None]:
    """The score at the end of each week, with the items up to then."""
    scores = []
    for week in weeks:
        end = datetime.combine(week + timedelta(days=7), datetime.min.time(), UTC)
        scores.append(score_of([i for i in items if i.at < end], criteria))
    return scores


def last_weeks(now: datetime) -> list[date]:
    today = now.astimezone(UTC).date()
    this_week = today - timedelta(days=today.weekday())
    return [this_week - timedelta(weeks=i) for i in range(WEEKS - 1, -1, -1)]


@dataclass
class _Topic:
    items: list[Item] = field(default_factory=list)
    errors: Counter = field(default_factory=Counter)
    latest_error: dict[str, tuple[datetime, uuid.UUID]] = field(default_factory=dict)


def _basis(items: list[Item]) -> schemas.ProgressBasis:
    exercises = [i for i in items if i.kind == "exercise"]
    quiz = [i for i in items if i.kind == "quiz"]
    return schemas.ProgressBasis(
        exercises_correct=sum(1 for i in exercises if i.value == 1.0),
        exercises_partial=sum(1 for i in exercises if i.value == 0.5),
        exercises_total=len(exercises),
        quiz_right=sum(1 for i in quiz if i.value == 1.0),
        quiz_total=len(quiz),
    )


def _error(
    code: str, count: int, data: _Topic, criteria: Criteria
) -> schemas.TopicError:
    latest, submission_id = data.latest_error[code]
    after = sorted(
        (i for i in data.items if i.kind == "exercise" and i.at > latest),
        key=lambda i: i.at,
    )
    run = overcome.run_since([i.value for i in after])
    return schemas.TopicError(
        error_type=code,
        count=count,
        latest_submission_id=submission_id,
        correct_since=run,
        overcome=run >= criteria.overcome_after,
    )


def _view(
    topic_id: uuid.UUID | None,
    name: str | None,
    data: _Topic,
    weeks: list[date],
    criteria: Criteria,
) -> schemas.TopicProgress:
    score = score_of(data.items, criteria)
    ranked = sorted(
        data.errors.items(),
        key=lambda kv: (-kv[1], -data.latest_error[kv[0]][0].timestamp(), kv[0]),
    )[:TOP_ERRORS]
    return schemas.TopicProgress(
        topic_id=topic_id,
        topic_name=name,
        level=level_of(len(data.items), score, criteria),  # type: ignore[arg-type]
        score=score,
        basis=_basis(_latest(data.items, criteria)),
        history=[
            schemas.WeekScore(week_start=week, score=value)
            for week, value in zip(
                weeks, history_of(data.items, weeks, criteria), strict=True
            )
        ],
        top_errors=[_error(code, count, data, criteria) for code, count in ranked],
        last_activity_at=max((i.at for i in data.items), default=None),
    )


def student_progress(
    session: Session,
    settings: Settings,
    course_id: uuid.UUID,
    student_id: uuid.UUID,
    now: datetime | None = None,
) -> schemas.Progress:
    """The same for the student and the teacher (constitution I)."""
    criteria = Criteria.of_course(session, course_id)
    weeks = last_weeks(now or datetime.now(UTC))
    by_topic: dict[uuid.UUID | None, _Topic] = defaultdict(_Topic)

    for topic_id, verdict, created_at in session.execute(
        select(
            ExerciseSubmission.topic_id,
            ExerciseSubmission.verdict,
            ExerciseSubmission.created_at,
        ).where(
            ExerciseSubmission.course_id == course_id,
            ExerciseSubmission.student_id == student_id,
            ExerciseSubmission.verdict.in_(EXERCISE_VALUE),
            ExerciseSubmission.is_stub.is_(False),
        )
    ):
        by_topic[topic_id].items.append(
            Item(at=created_at, value=EXERCISE_VALUE[verdict], kind="exercise")
        )

    for topic_id, correct, answered_at in session.execute(
        select(QuizItem.topic_id, QuizItem.correct, QuizItem.answered_at)
        .join(Quiz, Quiz.id == QuizItem.quiz_id)
        .where(
            Quiz.course_id == course_id,
            Quiz.student_id == student_id,
            QuizItem.answered_at.is_not(None),
        )
    ):
        by_topic[topic_id].items.append(
            Item(at=answered_at, value=1.0 if correct else 0.0, kind="quiz")
        )

    for topic_id, code, created_at, submission_id in session.execute(
        select(
            LearningRecordEntry.topic_id,
            LearningRecordEntry.error_type,
            LearningRecordEntry.created_at,
            LearningRecordEntry.submission_id,
        ).where(
            LearningRecordEntry.course_id == course_id,
            LearningRecordEntry.student_id == student_id,
        )
    ):
        data = by_topic[topic_id]
        data.errors[code] += 1
        if code not in data.latest_error or created_at > data.latest_error[code][0]:
            data.latest_error[code] = (created_at, submission_id)

    topics = session.scalars(
        select(Topic).where(Topic.course_id == course_id).order_by(Topic.position)
    ).all()
    views = [
        _view(topic.id, topic.name, by_topic.get(topic.id, _Topic()), weeks, criteria)
        for topic in topics
    ]
    # Graded work without a topic (or of a deleted one) is shown apart.
    known = {topic.id for topic in topics}
    loose = _Topic()
    for topic_id, data in by_topic.items():
        if topic_id not in known:
            loose.items.extend(data.items)
            loose.errors.update(data.errors)
            for code, latest in data.latest_error.items():
                if (
                    code not in loose.latest_error
                    or latest[0] > loose.latest_error[code][0]
                ):
                    loose.latest_error[code] = latest
    unassigned = _view(None, None, loose, weeks, criteria) if loose.items else None

    completed = (
        session.scalar(
            select(func.count()).where(
                Quiz.course_id == course_id,
                Quiz.student_id == student_id,
                Quiz.status == "completed",
            )
        )
        or 0
    )
    activity = [
        v.last_activity_at for v in [*views, unassigned] if v and v.last_activity_at
    ]
    return schemas.Progress(
        provisional=pedagogy.in_effect(session, course_id).provisional,
        criteria=schemas.ProgressCriteria(
            window=criteria.window,
            min_items=criteria.min_items,
            progressing=criteria.progressing,
            mastered=criteria.mastered,
        ),
        updated_at=max(activity, default=None),
        quizzes_completed=completed,
        topics=views,
        unassigned=unassigned,
    )
