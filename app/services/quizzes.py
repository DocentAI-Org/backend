"""Adaptive quizzes over the teacher's approved questions (S6, specs/006, 021).

Answering never calls the model. The level follows a provisional rule (FR-006): it is
the difficulty of the question shown. With the course's `quiz.adaptive` criterion, a
quiz starts at the level of the student's mastery (specs/021) and, on every topic,
favours their weak topics; otherwise, and without a score, at `quiz.start_level`.
`quiz.streak` right or wrong answers in a row aim one level up or down, and the level
moves only if the next question really is at another level.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.models import Enrolment, Quiz, QuizItem, QuizQuestion, Topic
from app.schemas import quizzes as schemas
from app.schemas.pedagogy import QuizCriteria
from app.schemas.progress import Progress
from app.services import consent, pedagogy, progress, tutor

MIN_LEVEL, MAX_LEVEL = 1, 3
# The start level of each mastery level (specs/021).
START = {"starting": 1, "progressing": 2, "mastered": 3}


@dataclass(frozen=True)
class Adaptation:
    level: int
    streak: int


def run(streak: int, correct: bool) -> int:
    """The signed streak including this answer: > 0 right in a row, < 0 wrong."""
    if correct:
        return streak + 1 if streak > 0 else 1
    return streak - 1 if streak < 0 else -1


def adapt(level: int, streak: int, correct: bool, streak_needed: int) -> Adaptation:
    """The level and streak after an answer; the streak restarts on a level change."""
    streak = run(streak, correct)
    if streak >= streak_needed and level < MAX_LEVEL:
        return Adaptation(level + 1, 0)
    if -streak >= streak_needed and level > MIN_LEVEL:
        return Adaptation(level - 1, 0)
    return Adaptation(level, streak)


def level_change(
    quiz: Quiz, shown: int, target: Adaptation, correct: bool
) -> schemas.DifficultyChange | None:
    """Why the next question is at another level, if it is (FR-002)."""
    if shown == quiz.level:
        return None
    streak_move = (
        target.level != quiz.level
        and (shown - quiz.level) * (target.level - quiz.level) > 0
    )
    return schemas.DifficultyChange(
        from_level=quiz.level,
        to_level=shown,
        reason=("correct_streak" if correct else "wrong_streak")
        if streak_move
        else "level_exhausted",
        streak=abs(run(quiz.streak, correct)),
    )


# --- Views -------------------------------------------------------------------------


def _current(quiz: Quiz) -> QuizItem | None:
    if quiz.status != "in_progress":
        return None
    return next((item for item in quiz.items if item.answered_at is None), None)


def _answered(quiz: Quiz) -> list[QuizItem]:
    return [item for item in quiz.items if item.answered_at is not None]


def _citations(item: QuizItem) -> list:
    question = item.question
    return [tutor.citation_view(c) for c in question.citations] if question else []


def _summary(quiz: Quiz) -> schemas.QuizSummary | None:
    if quiz.status != "completed":
        return None
    scores: dict[tuple[uuid.UUID | None, str], list[int]] = {}
    for item in _answered(quiz):
        score = scores.setdefault((item.topic_id, item.topic_name), [0, 0])
        score[0] += int(bool(item.correct))
        score[1] += 1
    return schemas.QuizSummary(
        score=sum(right for right, _ in scores.values()),
        total=sum(total for _, total in scores.values()),
        final_level=quiz.level,
        by_topic=[
            schemas.TopicScore(
                topic_id=topic_id, topic_name=name, correct=right, total=total
            )
            for (topic_id, name), (right, total) in scores.items()
        ],
    )


def quiz_view(quiz: Quiz) -> schemas.Quiz:
    current = _current(quiz)
    return schemas.Quiz(
        id=quiz.id,
        topic_id=quiz.topic_id,
        topic_name=quiz.topic_name,
        status=quiz.status,  # type: ignore[arg-type]
        question_count=quiz.question_count,
        answered_count=len(_answered(quiz)),
        level=quiz.level,
        start_basis=schemas.StartBasis(**quiz.start_basis)
        if quiz.start_basis
        else None,
        current=schemas.QuizQuestion(
            id=current.question_id,
            position=current.position,
            statement=current.statement,
            options=list(current.options),
            difficulty=current.difficulty,
            topic_name=current.topic_name,
        )
        if current and current.question_id
        else None,
        summary=_summary(quiz),
        started_at=quiz.started_at,
        completed_at=quiz.completed_at,
    )


def quiz_detail(quiz: Quiz) -> schemas.QuizDetail:
    return schemas.QuizDetail(
        **quiz_view(quiz).model_dump(),
        items=[
            schemas.AnsweredItem(
                position=item.position,
                statement=item.statement,
                options=list(item.options),
                difficulty=item.difficulty,
                topic_name=item.topic_name,
                choice=item.choice,  # type: ignore[arg-type]
                correct=bool(item.correct),
                correct_option=item.correct_option,
                explanation=item.explanation,
                citations=_citations(item),
                answered_at=item.answered_at,  # type: ignore[arg-type]
            )
            for item in _answered(quiz)
        ],
    )


# --- Picking questions -------------------------------------------------------------


def _approved(course_id: uuid.UUID, topic_id: uuid.UUID | None):
    query = select(QuizQuestion).where(
        QuizQuestion.course_id == course_id, QuizQuestion.status == "approved"
    )
    return query.where(QuizQuestion.topic_id == topic_id) if topic_id else query


def _times_answered(
    session: Session, quiz: Quiz, ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    rows = session.execute(
        select(QuizItem.question_id, func.count())
        .join(Quiz, Quiz.id == QuizItem.quiz_id)
        .where(
            Quiz.student_id == quiz.student_id,
            Quiz.course_id == quiz.course_id,
            QuizItem.question_id.in_(ids),
            QuizItem.answered_at.is_not(None),
        )
        .group_by(QuizItem.question_id)
    ).all()
    return dict(rows)  # type: ignore[arg-type]


def _criteria(session: Session, course_id: uuid.UUID) -> QuizCriteria:
    return pedagogy.in_effect(session, course_id).criteria.quiz


def _progress(session: Session, settings: Settings, quiz: Quiz) -> Progress:
    return progress.student_progress(session, settings, quiz.course_id, quiz.student_id)


def start_basis(
    current: Progress, topic_id: uuid.UUID | None, criteria: QuizCriteria
) -> tuple[int, schemas.StartBasis]:
    """The start level and why (specs/021): the topic's mastery, or for every topic the
    mean score of the scored topics read with the same thresholds."""
    if not criteria.adaptive:
        return criteria.start_level, schemas.StartBasis(
            reason="fixed", mastery_level=None, score=None
        )
    scores = [
        t.score
        for t in current.topics
        if t.score is not None and (topic_id is None or t.topic_id == topic_id)
    ]
    if not scores:
        return criteria.start_level, schemas.StartBasis(
            reason="no_score", mastery_level=None, score=None
        )
    score = sum(scores) / len(scores)
    thresholds = current.criteria
    level = (
        "mastered"
        if score >= thresholds.mastered
        else "progressing"
        if score >= thresholds.progressing
        else "starting"
    )
    return START[level], schemas.StartBasis(
        reason="mastery", mastery_level=level, score=score
    )


def weakness(current: Progress) -> dict[uuid.UUID | None, float]:
    """Each topic's score; a topic without one counts as `progressing` (specs/021)."""
    middle = current.criteria.progressing
    return {
        t.topic_id: t.score if t.score is not None else middle for t in current.topics
    }


def _pick(
    session: Session,
    quiz: Quiz,
    target: int,
    weak: dict[uuid.UUID | None, float] | None = None,
) -> QuizQuestion | None:
    """The level nearest to `target` first, then the questions answered least and, with
    `weak` (a quiz on every topic, specs/021), the topic with the lowest score."""
    used = {item.question_id for item in quiz.items}
    candidates = [
        q
        for q in session.scalars(_approved(quiz.course_id, quiz.topic_id))
        if q.id not in used
    ]
    if not candidates:
        return None
    answered = _times_answered(session, quiz, [q.id for q in candidates])
    return min(
        candidates,
        key=lambda q: (
            abs(q.difficulty - target),
            answered.get(q.id, 0),
            weak.get(q.topic_id, 1.0) if weak else 0.0,
            q.difficulty,
            q.created_at,
            q.id,
        ),
    )


def _add_item(session: Session, quiz: Quiz, question: QuizQuestion) -> None:
    session.add(
        QuizItem(
            quiz_id=quiz.id,
            question_id=question.id,
            position=len(quiz.items) + 1,
            topic_id=question.topic_id,
            topic_name=question.topic.name,
            statement=question.statement,
            options=list(question.options),
            correct_option=question.correct_option,
            explanation=question.explanation,
            difficulty=question.difficulty,
        )
    )
    session.flush()
    session.expire(quiz, ["items"])


def _complete(quiz: Quiz) -> None:
    quiz.status = "completed"
    quiz.completed_at = datetime.now(UTC)


# --- Flow --------------------------------------------------------------------------


def start(
    session: Session,
    settings: Settings,
    enrolment: Enrolment,
    topic_id: uuid.UUID | None,
) -> schemas.Quiz:
    consent.require(session, settings, enrolment.student_id)
    topic = session.get(Topic, topic_id) if topic_id else None
    if topic_id and (topic is None or topic.course_id != enrolment.course_id):
        raise not_found("Topic")
    available = (
        session.scalar(
            select(func.count()).select_from(
                _approved(enrolment.course_id, topic_id).subquery()
            )
        )
        or 0
    )
    if not available:
        raise ApiError(
            409, "no_questions", "The teacher has not published questions yet."
        )
    criteria = _criteria(session, enrolment.course_id)
    current = progress.student_progress(
        session, settings, enrolment.course_id, enrolment.student_id
    )
    level, basis = start_basis(current, topic_id, criteria)
    quiz = Quiz(
        course_id=enrolment.course_id,
        student_id=enrolment.student_id,
        topic_id=topic.id if topic else None,
        topic_name=topic.name if topic else None,
        question_count=min(criteria.length, available),
        level=level,
        streak=0,
        start_basis=basis.model_dump(),
    )
    session.add(quiz)
    session.flush()
    weak = weakness(current) if criteria.adaptive and topic is None else None
    question = _pick(session, quiz, quiz.level, weak)
    assert question is not None  # there are approved questions
    quiz.level = question.difficulty
    _add_item(session, quiz, question)
    session.refresh(quiz)
    return quiz_view(quiz)


def quiz_topics(session: Session, enrolment: Enrolment) -> list[schemas.QuizTopic]:
    """The course topics a quiz can be about: those with approved questions (FR-007)."""
    rows = session.execute(
        select(Topic.id, Topic.name, func.count(QuizQuestion.id))
        .join(QuizQuestion, QuizQuestion.topic_id == Topic.id)
        .where(
            Topic.course_id == enrolment.course_id,
            QuizQuestion.status == "approved",
        )
        .group_by(Topic.id, Topic.name, Topic.position)
        .order_by(Topic.position, Topic.name)
    ).all()
    return [
        schemas.QuizTopic(topic_id=topic_id, topic_name=name, question_count=count)
        for topic_id, name, count in rows
    ]


def get_quiz(session: Session, enrolment: Enrolment, quiz_id: uuid.UUID) -> Quiz:
    quiz = session.get(Quiz, quiz_id)
    if (
        quiz is None
        or quiz.course_id != enrolment.course_id
        or quiz.student_id != enrolment.student_id
    ):
        raise not_found("Quiz")
    return quiz


def list_quizzes(
    session: Session, enrolment: Enrolment, limit: int, offset: int
) -> tuple[list[schemas.Quiz], int]:
    query = select(Quiz).where(
        Quiz.course_id == enrolment.course_id,
        Quiz.student_id == enrolment.student_id,
    )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Quiz.started_at.desc(), Quiz.id).limit(limit).offset(offset)
    ).all()
    return [quiz_view(q) for q in rows], total


def answer(
    session: Session,
    settings: Settings,
    enrolment: Enrolment,
    quiz: Quiz,
    payload: schemas.QuizAnswer,
) -> schemas.AnswerResult:
    consent.require(session, settings, enrolment.student_id)
    if quiz.status == "completed":
        raise ApiError(409, "quiz_completed", "This quiz is already completed.")
    item = _current(quiz)
    if item is None or item.question_id != payload.question_id:
        raise ApiError(
            409, "not_current_question", "Answer the current question of the quiz."
        )
    item.choice = payload.choice
    correct = payload.choice == item.correct_option
    item.correct = correct
    item.answered_at = datetime.now(UTC)

    change: schemas.DifficultyChange | None = None
    if item.position >= quiz.question_count:
        _complete(quiz)
    else:
        criteria = _criteria(session, quiz.course_id)
        target = adapt(quiz.level, quiz.streak, correct, criteria.streak)
        weak = (
            weakness(_progress(session, settings, quiz))
            if criteria.adaptive and quiz.topic_id is None
            else None
        )
        question = _pick(session, quiz, target.level, weak)
        if question is None:
            # Questions were rejected meanwhile: the quiz ends with what was answered.
            quiz.question_count = item.position
            _complete(quiz)
        else:
            change = level_change(quiz, question.difficulty, target, correct)
            quiz.streak = 0 if change else run(quiz.streak, correct)
            quiz.level = question.difficulty
            _add_item(session, quiz, question)
    session.flush()
    session.refresh(quiz)
    return schemas.AnswerResult(
        correct=correct,
        correct_option=item.correct_option,
        explanation=item.explanation,
        citations=_citations(item),
        difficulty_change=change,
        quiz=quiz_view(quiz),
    )
