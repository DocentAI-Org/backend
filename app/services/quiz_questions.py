"""Quiz questions drafted by the AI from a topic's material and reviewed by the
teacher (T7, specs/006). Only approved questions reach students."""

import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import and_, case, func, or_, select, true
from sqlalchemy.orm import Session

from app.core.config import Route, Settings
from app.core.errors import ApiError, not_found
from app.core.search import matches
from app.core.types import KeyCheck
from app.llm.client import ChatResult, LLMClient, LLMError
from app.llm.prompts import load_labels, load_prompt
from app.models import (
    Citation,
    Course,
    Fragment,
    QuizItem,
    QuizQuestion,
    Topic,
    TopicAssignment,
    TutorSettings,
)
from app.schemas import quizzes as schemas
from app.services import ai_settings, exercises, interactions, tutor
from app.services.retrieval import Hit, retrieve

logger = logging.getLogger(__name__)

OPTIONS = 4
LETTERS = "ABCD"
_LETTER_PREFIX = re.compile(r"([A-Da-d])\s*[).:]\s+")
DEFAULT_DIFFICULTY = 2
STATEMENT_CHARS = 1000
OPTION_CHARS = 300
# More material than a tutor reply: the questions should cover the topic.
TOPIC_FRAGMENTS = 8


@dataclass
class Draft:
    statement: str
    options: list[str]
    correct_option: int
    explanation: str
    difficulty: int
    cited_indexes: list[int]


def statement_key(statement: str) -> str:
    """Compares statements ignoring case, spacing and final punctuation."""
    return re.sub(r"\s+", " ", statement).strip().rstrip(".?¿!¡").casefold()


def _text(value: object, limit: int) -> str | None:
    if isinstance(value, str) and value.strip():
        return exercises.without_fragment_refs(value.strip())[:limit] or None
    return None


def _correct_index(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value < OPTIONS else None
    if isinstance(value, str):
        letter = value.strip().rstrip(").").upper()
        if len(letter) == 1 and letter in LETTERS:
            return LETTERS.index(letter)
    return None


def _without_letter(option: str, position: int) -> str:
    """ "B) 2x - 6" -> "2x - 6": the interface shows its own letters."""
    match = _LETTER_PREFIX.match(option)
    if match and match.group(1).upper() == LETTERS[position]:
        return option[match.end() :]
    return option


def _options(value: object) -> list[str] | None:
    if not isinstance(value, list) or len(value) != OPTIONS:
        return None
    if not all(isinstance(option, str) and option.strip() for option in value):
        return None
    options = [
        _without_letter(option.strip(), i).strip()[:OPTION_CHARS]
        for i, option in enumerate(value)
    ]
    if not all(options) or len({o.casefold() for o in options}) != OPTIONS:
        return None
    return options


def spread(options: list[str], correct: int, target: int) -> tuple[list[str], int]:
    """Rotates the options so the correct one is at `target`.

    Small models put the right answer in the same place almost every time (B in 11 of
    15 questions in the validation run); rotating keeps the distractors' order.
    """
    shift = (target - correct) % OPTIONS
    rotated = [options[(i - shift) % OPTIONS] for i in range(OPTIONS)]
    return rotated, target


def _difficulty(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 3:
        return value
    return DEFAULT_DIFFICULTY


def validate_drafts(
    data: dict, fragment_count: int, limit: int, existing: set[str] | None = None
) -> list[Draft]:
    """The usable drafts, grounded and well formed (FR-003); the rest are dropped."""
    drafts = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(drafts, list):
        return []
    seen = set(existing or ())
    accepted: list[Draft] = []
    for item in drafts:
        if len(accepted) == limit:
            break
        if not isinstance(item, dict):
            continue
        statement = _text(item.get("statement"), STATEMENT_CHARS)
        explanation = _text(item.get("explanation"), STATEMENT_CHARS)
        options = _options(item.get("options"))
        correct = _correct_index(item.get("correct"))
        cited = item.get("cited")
        if (
            statement is None
            or explanation is None
            or options is None
            or correct is None
        ):
            continue
        if not isinstance(cited, list):
            continue
        indexes = tutor.cited_fragment_indexes(cited, fragment_count)
        key = statement_key(statement)
        if not indexes or key in seen:
            continue
        seen.add(key)
        options, correct = spread(options, correct, len(accepted) % OPTIONS)
        accepted.append(
            Draft(
                statement=statement,
                options=options,
                correct_option=correct,
                explanation=explanation,
                difficulty=_difficulty(item.get("difficulty")),
                cited_indexes=indexes,
            )
        )
    return accepted


# --- Key check (specs/025) ----------------------------------------------------------

CheckedKey = tuple[KeyCheck, list[int]]


def check_keys(
    llm: LLMClient,
    language: str,
    route: Route | None,
    hits: list[Hit],
    drafts: list[Draft],
) -> tuple[list[CheckedKey | None], ChatResult | None]:
    """Each draft solved from the same material without its key: `agrees`, `disagrees`,
    `several` or `no_right`, with the options found right; None where the reply is
    unusable. The drafts never change: the teacher decides."""
    questions = "\n\n".join(
        f"{number}. {draft.statement}\n"
        + "\n".join(f"{LETTERS[i]}) {option}" for i, option in enumerate(draft.options))
        for number, draft in enumerate(drafts, start=1)
    )
    try:
        result = llm.chat_json(
            load_prompt("quiz_key_check", language),
            [
                {
                    "role": "user",
                    "content": f"{tutor.material_block(hits)}\n\n"
                    f"<preguntas>\n{questions}\n</preguntas>",
                }
            ],
            temperature=0.0,
            task="questions",
            route=route,
        )
    except LLMError:
        logger.warning("Quiz key check failed")
        return [None] * len(drafts), None
    right = _checked_options(result.data, len(drafts))
    return [
        None if found is None else (_verdict(found, draft.correct_option), found)
        for draft, found in zip(drafts, right, strict=True)
    ], result


def _checked_options(data: object, count: int) -> list[list[int] | None]:
    found: list[list[int] | None] = [None] * count
    answers = data.get("answers") if isinstance(data, dict) else None
    for answer in answers if isinstance(answers, list) else []:
        if not isinstance(answer, dict):
            continue
        number = answer.get("question")
        letters = answer.get("right")
        letters = [letters] if isinstance(letters, str) else letters
        if not isinstance(number, int) or not 1 <= number <= count:
            continue
        # An empty list is an answer: no option is right.
        if not isinstance(letters, list):
            continue
        indexes = [_correct_index(letter) for letter in letters]
        if any(index is None for index in indexes):
            continue
        found[number - 1] = sorted({i for i in indexes if i is not None})
    return found


def _verdict(right: list[int], key: int) -> KeyCheck:
    if not right:
        return "no_right"
    if len(right) > 1:
        return "several"
    return "agrees" if right == [key] else "disagrees"


def build_prompt(
    settings: Settings, tutor_settings: TutorSettings, teacher: str | None = None
) -> str:
    labels = load_labels("policies", settings.tutor_language)
    return load_prompt("quiz_questions", settings.tutor_language).format(
        level=labels[f"level.{tutor_settings.level}"],
        tone=labels[f"tone.{tutor_settings.tone}"],
        teacher=tutor.teacher_block(settings, teacher),
    )


def level_plan(count: int) -> dict[int, int]:
    """How many questions to ask for at each level, spread evenly; spare ones go to the
    middle level first (left alone, the local model labelled every draft as basic)."""
    base, spare = divmod(count, 3)
    extra = {0: (), 1: (2,), 2: (1, 2)}[spare]
    return {level: base + (level in extra) for level in (1, 2, 3)}


def build_messages(hits: list[Hit], topic: Topic, count: int) -> list[dict[str, str]]:
    """Only course material and the topic name; no personal data."""
    plan = level_plan(count)
    return [
        {
            "role": "user",
            "content": f"{tutor.material_block(hits)}\n\n"
            f"<tema>\n{topic.name}\n</tema>\n\n"
            f"Prepara {count} preguntas sobre este tema: {plan[1]} de dificultad 1, "
            f"{plan[2]} de dificultad 2 y {plan[3]} de dificultad 3.",
        }
    ]


def topic_material(
    session: Session, llm: LLMClient, settings: Settings, topic: Topic
) -> list[Hit]:
    """The topic's confirmed material; without any, the material closest to its name."""
    assignments = session.execute(
        select(TopicAssignment.document_id, TopicAssignment.section).where(
            TopicAssignment.topic_id == topic.id,
            TopicAssignment.status == "confirmed",
        )
    ).all()
    if not assignments:
        ai = ai_settings.in_effect(session, settings, topic.course_id)
        return retrieve(
            session,
            llm,
            topic.course_id,
            topic.name,
            TOPIC_FRAGMENTS,
            ai.retrieval.min_similarity,
        )
    assigned = or_(
        *(
            and_(
                Fragment.document_id == document_id,
                Fragment.section == section if section else true(),
            )
            for document_id, section in assignments
        )
    )
    # The teacher said this material is the topic: no similarity threshold.
    return retrieve(
        session,
        llm,
        topic.course_id,
        topic.name,
        TOPIC_FRAGMENTS,
        min_similarity=-1.0,
        where=(assigned,),
    )


# --- Views -------------------------------------------------------------------------


def _answer_stats(
    session: Session, ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    if not ids:
        return {}
    rows = session.execute(
        select(
            QuizItem.question_id,
            func.count(),
            func.count().filter(QuizItem.correct.is_(True)),
        )
        .where(QuizItem.question_id.in_(ids), QuizItem.answered_at.is_not(None))
        .group_by(QuizItem.question_id)
    ).all()
    return {question_id: (total, right) for question_id, total, right in rows}  # type: ignore[misc]  (each row's question is one of ids, never None)


def question_views(
    session: Session, questions: list[QuizQuestion]
) -> list[schemas.TeacherQuestion]:
    stats = _answer_stats(session, [q.id for q in questions])
    views = []
    for question in questions:
        answered, right = stats.get(question.id, (0, 0))
        views.append(
            schemas.TeacherQuestion(
                id=question.id,
                topic_id=question.topic_id,
                topic_name=question.topic.name,
                statement=question.statement,
                options=list(question.options),
                correct_option=question.correct_option,
                explanation=question.explanation,
                difficulty=question.difficulty,
                status=question.status,
                key_check=question.key_check,
                key_check_options=list(question.key_check_options or []),
                origin=question.origin,
                citations=[tutor.citation_view(c) for c in question.citations],
                answered_count=answered,
                correct_rate=right / answered if answered else None,
                reviewed_at=question.reviewed_at,
                created_at=question.created_at,
            )
        )
    return views


# --- Generation --------------------------------------------------------------------


def generate(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    course: Course,
    topic: Topic,
    count: int,
) -> schemas.GeneratedQuestions:
    started = time.perf_counter()
    try:
        return _generate(session, llm, settings, course, topic, count, started)
    except Exception as exc:
        if not isinstance(exc, LLMError):
            logger.exception("Question generation failed in course %s", course.id)
        session.rollback()
        interactions.record(
            session,
            settings,
            course_id=course.id,
            student_id=None,
            kind="quiz_generation",
            question=topic.name,
            fragment_ids=[],
            outcome="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_code="tutor_unavailable",
        )
        session.commit()
        raise ApiError(
            503, "tutor_unavailable", "The tutor could not draft the questions."
        ) from None


def _generate(
    session: Session,
    llm: LLMClient,
    settings: Settings,
    course: Course,
    topic: Topic,
    count: int,
    started: float,
) -> schemas.GeneratedQuestions:
    hits = topic_material(session, llm, settings, topic)
    result: ChatResult | None = None
    drafts: list[Draft] = []
    checks: list[CheckedKey | None] = []
    check_result: ChatResult | None = None
    if hits:
        tutor_settings = session.get(TutorSettings, course.id)
        assert tutor_settings is not None
        ai = ai_settings.in_effect(session, settings, course.id)
        result = llm.chat_json(
            build_prompt(settings, tutor_settings, ai.instruction("questions")),
            build_messages(hits, topic, count),
            task="questions",
            route=ai.route("questions"),
        )
        existing = {
            statement_key(s)
            for s in session.scalars(
                select(QuizQuestion.statement).where(
                    QuizQuestion.course_id == course.id
                )
            )
        }
        drafts = validate_drafts(result.data, len(hits), count, existing)
        if drafts and settings.quiz_key_check:
            checks, check_result = check_keys(
                llm, settings.tutor_language, ai.route("questions"), hits, drafts
            )

    rows = [
        QuizQuestion(
            course_id=course.id,
            topic_id=topic.id,
            statement=draft.statement,
            options=draft.options,
            correct_option=draft.correct_option,
            explanation=draft.explanation,
            difficulty=draft.difficulty,
            key_check=check[0] if check else None,
            key_check_options=check[1] if check else None,
        )
        for draft, check in zip(drafts, checks or [None] * len(drafts), strict=True)
    ]
    session.add_all(rows)
    session.flush()
    for row, draft in zip(rows, drafts, strict=True):
        session.add_all(
            Citation(
                question_id=row.id,
                fragment_id=hits[i].fragment.id,
                document_name=hits[i].document_name,
                location_label=hits[i].fragment.location_label,
                position=position,
            )
            for position, i in enumerate(draft.cited_indexes, start=1)
        )
    kind = "answer" if rows else "no_source"
    interactions.record(
        session,
        settings,
        course_id=course.id,
        student_id=None,
        kind="quiz_generation",
        question=f"{topic.name} ({count})",
        fragment_ids=[hit.fragment.id for hit in hits],
        outcome=kind,
        answer="\n".join(row.statement for row in rows) or None,
        model=result.model if result else None,
        input_tokens=sum(r.input_tokens for r in (result, check_result) if r),
        output_tokens=sum(r.output_tokens for r in (result, check_result) if r),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
    session.flush()
    for row in rows:
        session.refresh(row)
    return schemas.GeneratedQuestions(
        kind=kind,
        questions=question_views(session, rows),
    )


# --- Review ------------------------------------------------------------------------


def get_question(
    session: Session, course: Course, question_id: uuid.UUID
) -> QuizQuestion:
    question = session.get(QuizQuestion, question_id)
    if question is None or question.course_id != course.id:
        raise not_found("Question")
    return question


QuestionSort = Literal["default", "recent"]


def list_questions(
    session: Session,
    course: Course,
    status: str | None,
    topic_id: uuid.UUID | None,
    limit: int,
    offset: int,
    q: str | None = None,
    sort: QuestionSort = "default",
) -> schemas.QuestionPage:
    topic_name = select(Topic.name).where(Topic.id == QuizQuestion.topic_id)
    scope = select(QuizQuestion).where(
        QuizQuestion.course_id == course.id,
        matches(q, QuizQuestion.statement, topic_name.scalar_subquery()),
    )
    if topic_id:
        scope = scope.where(QuizQuestion.topic_id == topic_id)
    counted = _counts(session, scope)
    query = scope.where(QuizQuestion.status == status) if status else scope
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    # Pending first, and among them the drafts whose key the check doubts (specs/025).
    pending_first = case(
        (
            and_(
                QuizQuestion.status == "pending",
                QuizQuestion.key_check.in_(("disagrees", "several", "no_right")),
            ),
            0,
        ),
        (QuizQuestion.status == "pending", 1),
        else_=2,
    )
    order = (QuizQuestion.created_at.desc(), QuizQuestion.id)
    rows = session.scalars(
        query.order_by(*((pending_first, *order) if sort == "default" else order))
        .limit(limit)
        .offset(offset)
    ).all()
    return schemas.QuestionPage(
        items=question_views(session, list(rows)),
        total=total,
        limit=limit,
        offset=offset,
        counts=schemas.QuestionCounts(**counted),
    )


def _counts(session: Session, scope) -> dict[str, int]:
    sub = scope.subquery()
    rows = session.execute(select(sub.c.status, func.count()).group_by(sub.c.status))
    counts = {"pending": 0, "approved": 0, "rejected": 0}
    counts.update({status: total for status, total in rows})
    return counts


CONTENT_FIELDS = ("statement", "options", "correct_option", "explanation", "difficulty")


def update_question(
    session: Session,
    teacher_id: uuid.UUID,
    question: QuizQuestion,
    payload: schemas.QuestionUpdate,
) -> schemas.TeacherQuestion:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    edited = set()
    for field in CONTENT_FIELDS:
        if field in changes and changes[field] != getattr(question, field):
            setattr(question, field, changes[field])
            edited.add(field)
    if edited:
        question.origin = "edited"
    if edited & {"options", "correct_option"}:
        # The check was of the old options or key.
        question.key_check = None
        question.key_check_options = None
    if "status" in changes:
        question.status = changes["status"]
        question.reviewed_by = teacher_id
        question.reviewed_at = datetime.now(UTC)
    session.flush()
    session.refresh(question)
    [view] = question_views(session, [question])
    return view
