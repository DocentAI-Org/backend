"""Courses, material and weeks of student activity for the local sample data.

Mirrors the frontend's demo data (`tests/app/mock-api/demo.ts`): the same people,
courses and shape of activity, from a seeded random generator per student and course,
dated relative to now. Material goes through the app's own pipeline (store_upload and
process_document: real files, real embeddings); activity rows are written directly, as
the services that normally write them would, citing the fragments of each topic's
section. Nothing here calls the chat model.
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_session_factory
from app.integrations.storage import StorageClient
from app.llm.client import LLMClient
from app.models import (
    Citation,
    ConsentEvent,
    Conversation,
    Course,
    CourseFavorite,
    CourseTag,
    CourseTagLink,
    Document,
    Enrolment,
    ExerciseSubmission,
    Fragment,
    LearningRecordEntry,
    Message,
    Profile,
    Quiz,
    QuizItem,
    QuizQuestion,
    TeacherFlag,
    TestAnswer,
    TestAttempt,
    TestPhase,
    TestQuestion,
    Topic,
    TopicAssignment,
    TutorSettings,
)
from app.services import documents, interactions
from app.services.quizzes import run
from app.services.tutor import no_source_text
from scripts.seed_material import build_file, course_content, people, section_key

DAY = timedelta(days=1)

# What happens to each course's third, supplementary document.
SUPPLEMENT = {
    "algebra-3b": "validated",
    "geometria-3b": "pending_validation",
    "funciones-4a": "pending_validation",
    "estadistica-4a": "processing",
    "lengua-3b": "validated",
    "comentario-4a": "excluded",
    "siglo-de-oro-4a": "pending_validation",
    "edad-moderna-3b": "error",
    "contemporanea-4a": "validated",
    "calculo-uni": "pending_validation",
    "programacion-uni": "validated",
    "bases-datos-uni": "pending_validation",
}

# Pre/post tests: which phases have run, per course.
TESTS: dict[str, dict[str, str]] = {
    "algebra-3b": {"pre": "closed", "post": "open"},
    "funciones-4a": {"pre": "open"},
    "programacion-uni": {"pre": "closed"},
}

FAVORITES = {
    "profesora@docentai.local": ["algebra-3b", "funciones-4a"],
    "javier.molina@example.org": ["lengua-3b"],
    "andres.navarro@example.org": ["programacion-uni"],
    "alumno@docentai.local": ["algebra-3b"],
}
LUCAS = "alumno@docentai.local"

PRAISE = [
    "Respuesta correcta: has seguido bien todos los pasos.",
    "¡Bien hecho! La respuesta es correcta y está bien justificada.",
    "Correcto. El planteamiento es claro y el resultado, exacto.",
    "Respuesta correcta y bien presentada.",
]

CORRECTIONS = [
    (
        "poor",
        "La respuesta es correcta, pero conviene remitir al ejemplo resuelto del "
        "apartado: lo trabajamos así en clase.",
    ),
    (
        "poor",
        "Demasiado larga para este nivel. Mejor en dos pasos cortos y con un ejemplo.",
    ),
    (
        "incorrect",
        "Falta un matiz importante que vimos en clase; lo he añadido al material de "
        "la unidad.",
    ),
]


@dataclass(frozen=True)
class Behaviour:
    """How much a student does, how well and until when."""

    chats: tuple[int, int]
    exercises: tuple[int, int]
    quizzes: tuple[int, int]
    correct: float
    partial: float
    quiz_right: float
    idle: tuple[int, int]


PROFILES = [
    ("engaged", 0.22),
    ("regular", 0.43),
    ("struggling", 0.18),
    ("fading", 0.11),
    ("silent", 0.06),
]
BEHAVIOUR = {
    "engaged": Behaviour((4, 7), (9, 14), (2, 4), 0.78, 0.12, 0.85, (0, 2)),
    "regular": Behaviour((2, 4), (5, 9), (1, 2), 0.6, 0.18, 0.65, (0, 5)),
    "struggling": Behaviour((3, 6), (7, 11), (1, 2), 0.25, 0.2, 0.4, (0, 4)),
    "fading": Behaviour((1, 3), (2, 5), (0, 1), 0.5, 0.2, 0.55, (9, 20)),
    "silent": Behaviour((0, 0), (0, 0), (0, 0), 0, 0, 0, (0, 0)),
}


class Rng(random.Random):
    """Seeded by a string, so every run builds the same data (not for security)."""

    def between(self, bounds: tuple[int, int]) -> int:
        return self.randint(*bounds)

    def chance(self, p: float) -> bool:
        return self.random() < p


def profile_of(rng: Rng) -> str:
    roll = rng.random()
    for profile, weight in PROFILES:
        roll -= weight
        if roll < 0:
            return profile
    return "regular"


def new_id() -> uuid.UUID:
    return uuid.uuid4()


@dataclass
class TopicSeed:
    topic: Topic
    content: dict[str, Any]
    fragment: Fragment
    document_name: str


@dataclass
class CourseSeed:
    key: str
    course: Course
    teacher: Profile
    created: datetime
    content: dict[str, Any]
    policy: str
    topics: list[TopicSeed] = field(default_factory=list)
    approved: dict[uuid.UUID, list[QuizQuestion]] = field(default_factory=dict)
    test_questions: list[TestQuestion] = field(default_factory=list)
    phases: dict[str, TestPhase] = field(default_factory=dict)
    answers: list[Message] = field(default_factory=list)
    mistakes: list[ExerciseSubmission] = field(default_factory=list)


@dataclass
class Window:
    """When a student was active in a course, and the generator for their activity."""

    rng: Rng
    seed: CourseSeed
    student: Profile
    behaviour: Behaviour
    start: datetime
    end: datetime
    now: datetime

    def during(self, moment: datetime) -> datetime:
        """A moment of that day between 8:00 and 22:00 UTC, never in the future."""
        day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        at = day + timedelta(hours=8 + self.rng.random() * 14)
        return min(self.now - timedelta(minutes=1), at)

    def when(self, recent: bool = False) -> datetime:
        start = max(self.start, self.end - 13 * DAY) if recent else self.start
        span = max(timedelta(0), self.end - start)
        return self.during(start + self.rng.random() * span)

    def topic_at(self, moment: datetime, reviewed_only: bool = False) -> TopicSeed:
        """Topics follow the course calendar: later dates, later topics."""
        topics = self.seed.topics
        share = (moment - self.seed.created) / (self.now - self.seed.created)
        last = len(topics) - (2 if reviewed_only else 1)
        index = int(share * len(topics) + (self.rng.random() - 0.5))
        return topics[max(0, min(last, index))]


def _cite(seed: TopicSeed, **owner: uuid.UUID) -> Citation:
    return Citation(
        id=new_id(),
        fragment_id=seed.fragment.id,
        document_name=seed.document_name,
        location_label=seed.fragment.location_label,
        position=1,
        **owner,
    )


class Seeder:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        llm: LLMClient,
        storage: StorageClient,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.llm = llm
        self.storage = storage
        self.now = now or datetime.now(UTC)
        self.traits: dict[str, str] = {}
        self.consented = set(session.scalars(select(ConsentEvent.student_id)))

    def days_ago(self, days: float) -> datetime:
        return self.now - days * DAY

    # --- Courses and material ------------------------------------------------------

    def course(
        self,
        index: int,
        key: str,
        teacher: Profile,
        students: list[Profile],
        leaver: Profile,
    ) -> CourseSeed:
        meta = next(c for c in people()["courses"] if c["key"] == key)
        content = course_content(key)
        created = self.days_ago(68 - index * 0.5)
        course = Course(
            id=new_id(),
            teacher_id=teacher.id,
            name=content["name"],
            description=content["description"],
            class_code=meta["class_code"],
            class_code_active=key != "calculo-uni",
            created_at=created,
        )
        self.session.add(course)
        self.session.flush()
        self.session.add(
            TutorSettings(
                course_id=course.id, **meta["settings"], updated_at=created + DAY
            )
        )
        seed = CourseSeed(
            key, course, teacher, created, content, meta["settings"]["solution_policy"]
        )
        fragments = self.material(seed, index)
        self.topics(seed, fragments)
        self.question_bank(seed, index)
        self.tests(seed)
        for student in students:
            self.student(seed, student, revoked=student.id == leaver.id)
        self.flags(seed)
        self.session.commit()
        return seed

    def material(self, seed: CourseSeed, index: int) -> dict[tuple[str, str], Fragment]:
        """Two main documents validated; the supplement as SUPPLEMENT says."""
        fragments: dict[tuple[str, str], Fragment] = {}
        for n, source in enumerate(seed.content["documents"]):
            outcome = "validated" if n < 2 else SUPPLEMENT[seed.key]
            uploaded = (
                seed.created + (n + 1) * timedelta(hours=1)
                if n < 2
                else self.days_ago(2 + index % 5)
            )
            document = self.upload(seed, source, outcome, uploaded)
            for fragment in self.session.scalars(
                select(Fragment)
                .where(Fragment.document_id == document.id)
                .order_by(Fragment.position)
            ):
                fragments.setdefault((source["file_name"], fragment.section), fragment)
        return fragments

    def upload(
        self,
        seed: CourseSeed,
        source: dict[str, Any],
        outcome: str,
        uploaded: datetime,
    ) -> Document:
        content = build_file(seed.content["name"], source)
        document = documents.store_upload(
            self.session,
            self.storage,
            self.settings,
            seed.course,
            seed.teacher,
            source["file_name"],
            content,
        )
        # process_document works in its own session, as the background task does.
        self.session.commit()
        if outcome not in ("processing", "error"):
            documents.process_document(
                get_session_factory(),
                self.llm,
                document.id,
                document.file_type,
                content,
            )
        self.session.refresh(document)
        if outcome not in ("processing", "error") and (
            document.processing_status != "ready"
        ):
            raise RuntimeError(
                f"{source['file_name']} was not processed ({document.error_reason})."
            )
        document.uploaded_at = uploaded
        if outcome == "processing":
            # The API marks it processing_interrupted when it next starts.
            document.processing_status = "processing"
        elif outcome == "error":
            document.processing_status = "error"
            document.error_reason = "no_readable_text"
        elif outcome == "validated":
            document.validation_status = "validated"
            document.validated_by = seed.teacher.id
            document.validated_at = uploaded + DAY
        elif outcome == "excluded":
            document.validation_status = "excluded"
        return document

    def topics(
        self, seed: CourseSeed, fragments: dict[tuple[str, str], Fragment]
    ) -> None:
        """Each topic confirmed on its section; the validated supplement suggested."""
        names = {d["file_name"]: d for d in seed.content["documents"]}
        for position, content in enumerate(seed.content["topics"], start=1):
            source = names[content["document"]]
            section = next(
                s for s in source["sections"] if s["title"] == content["section"]
            )
            key = section_key(source, section)
            fragment = fragments[(source["file_name"], key)]
            topic = Topic(
                id=new_id(),
                course_id=seed.course.id,
                name=content["name"],
                position=position,
                created_at=seed.created + 2 * timedelta(hours=1),
            )
            self.session.add(topic)
            self.session.flush()
            self.session.add(
                TopicAssignment(
                    id=new_id(),
                    course_id=seed.course.id,
                    topic_id=topic.id,
                    document_id=fragment.document_id,
                    section=key,
                    status="confirmed",
                    confirmed_by=seed.teacher.id,
                    confirmed_at=topic.created_at,
                    created_at=topic.created_at,
                )
            )
            seed.topics.append(TopicSeed(topic, content, fragment, source["file_name"]))
        if SUPPLEMENT[seed.key] == "validated":
            supplement = seed.content["documents"][2]
            first = supplement["sections"][0]
            fragment = fragments[
                (supplement["file_name"], section_key(supplement, first))
            ]
            self.session.add(
                TopicAssignment(
                    id=new_id(),
                    course_id=seed.course.id,
                    topic_id=seed.topics[1].topic.id,
                    document_id=fragment.document_id,
                    section=fragment.section,
                    status="suggested",
                    created_at=self.days_ago(1),
                )
            )

    def question_bank(self, seed: CourseSeed, index: int) -> None:
        """Reviewed for the first four topics; the last one's drafts still pending."""
        last = len(seed.topics) - 1
        for n, topic in enumerate(seed.topics):
            created = seed.created + (n * 9 + 2) * DAY
            approved: list[QuizQuestion] = []
            for k, draft in enumerate(topic.content["quiz"]):
                status = (
                    "pending"
                    if n == last
                    else "rejected"
                    if n == 3 and k == 2 and index % 3 == 0
                    else "approved"
                )
                question = QuizQuestion(
                    id=new_id(),
                    course_id=seed.course.id,
                    topic_id=topic.topic.id,
                    statement=draft["statement"],
                    options=draft["options"],
                    correct_option=draft["correct"],
                    explanation=draft["explanation"],
                    difficulty=draft["difficulty"],
                    status=status,
                    origin="edited" if (n + k) % 4 == 3 else "ai",
                    reviewed_by=None if status == "pending" else seed.teacher.id,
                    reviewed_at=None if status == "pending" else created + DAY,
                    created_at=created,
                )
                self.session.add(question)
                self.session.add(_cite(topic, question_id=question.id))
                if status == "approved":
                    approved.append(question)
            seed.approved[topic.topic.id] = approved
        self.session.flush()

    def tests(self, seed: CourseSeed) -> None:
        """Pre/post test: the first approved question of each reviewed topic."""
        plan = TESTS.get(seed.key)
        if plan is None:
            return
        pre_opened = seed.created + 3 * DAY
        for position, topic in enumerate(seed.topics[:4], start=1):
            source = seed.approved[topic.topic.id][0]
            question = TestQuestion(
                id=new_id(),
                course_id=seed.course.id,
                topic_id=topic.topic.id,
                topic_name=topic.topic.name,
                position=position,
                statement=source.statement,
                options=list(source.options),
                correct_option=source.correct_option,
                created_at=seed.created + 2 * DAY,
            )
            self.session.add(question)
            seed.test_questions.append(question)
        seed.phases["pre"] = TestPhase(
            course_id=seed.course.id,
            phase="pre",
            status=plan["pre"],
            opened_at=pre_opened,
            closed_at=pre_opened + 10 * DAY if plan["pre"] == "closed" else None,
        )
        if "post" in plan:
            seed.phases["post"] = TestPhase(
                course_id=seed.course.id,
                phase="post",
                status="open",
                opened_at=self.days_ago(5),
                closed_at=None,
            )
        self.session.add_all(seed.phases.values())
        self.session.flush()

    # --- Students ------------------------------------------------------------------

    def trait(self, student: Profile) -> str:
        email = student.email or student.pseudonym_code or str(student.id)
        if email not in self.traits:
            self.traits[email] = profile_of(Rng(f"trait:{email}"))
        return self.traits[email]

    def student(self, seed: CourseSeed, student: Profile, revoked: bool) -> None:
        email = student.email or (student.pseudonym_code or "").lower()
        rng = Rng(f"{seed.key}:{email}")
        lucas = email == LUCAS
        profile = self.trait(student) if rng.chance(0.7) else profile_of(rng)
        if lucas:
            profile = "struggling" if seed.key == "algebra-3b" else "regular"
        joined = seed.created + (rng.between((1, 6)) + rng.random()) * DAY
        active = profile != "silent"
        self.session.add(
            Enrolment(
                id=new_id(),
                course_id=seed.course.id,
                student_id=student.id,
                status="revoked" if revoked else "active",
                joined_at=joined,
                disclosure_acknowledged_at=joined + timedelta(minutes=10)
                if active
                else None,
            )
        )
        if student.id not in self.consented:
            self.consented.add(student.id)
            self.session.add(
                ConsentEvent(
                    id=new_id(),
                    student_id=student.id,
                    action="given",
                    version=self.settings.consent_version,
                    created_at=joined,
                )
            )
        if not active:
            return
        behaviour = BEHAVIOUR[profile]
        # Lucas has not been back to Álgebra for 9 days, and most of his exercises
        # went wrong.
        idle = (
            9
            if lucas and seed.key == "algebra-3b"
            else rng.between(behaviour.idle) + rng.random()
        )
        window = Window(
            rng,
            seed,
            student,
            behaviour,
            start=max(joined, self.days_ago(56)),
            end=self.days_ago(idle),
            now=self.now,
        )
        self.chats(window)
        self.exercises(window, struggling=profile == "struggling")
        self.quizzes(window)
        if not revoked:
            self.test_attempts(window, lucas)

    def _log(self, w: Window, moment: datetime, **fields: Any) -> None:
        log = interactions.record(
            self.session,
            self.settings,
            course_id=w.seed.course.id,
            student_id=w.student.id,
            model=self.llm.chat_model,
            input_tokens=w.rng.randint(700, 1900),
            output_tokens=w.rng.randint(60, 320),
            latency_ms=w.rng.randint(1500, 9000),
            **fields,
        )
        log.created_at = moment

    def chats(self, w: Window) -> None:
        for _ in range(w.rng.between(w.behaviour.chats)):
            at = w.when()
            conversation = Conversation(
                id=new_id(),
                course_id=w.seed.course.id,
                student_id=w.student.id,
                started_at=at,
            )
            self.session.add(conversation)
            hints = 0
            for k in range(w.rng.randint(1, 3)):
                if k:
                    at += timedelta(minutes=2 + w.rng.random() * 6)
                at, hints = self.exchange(w, conversation, at, k, hints)
            conversation.last_message_at = at

    def exchange(
        self, w: Window, conversation: Conversation, at: datetime, k: int, hints: int
    ) -> tuple[datetime, int]:
        """A student question and the tutor's reply; returns the reply's time and
        the run of hints so far."""
        topic = w.topic_at(at)
        off_topic = w.rng.chance(0.07)
        pair = None if off_topic else w.rng.choice(topic.content["questions"])
        text = pair["question"] if pair else w.rng.choice(w.seed.content["off_topic"])
        common = {"conversation_id": conversation.id, "status": "sent"}
        self.session.add(
            Message(
                id=new_id(),
                author="student",
                kind="question",
                text=text,
                counts_toward_limit=True,
                created_at=at,
                **common,
            )
        )
        at += timedelta(seconds=20 + w.rng.random() * 40)
        hint = w.seed.policy == "hints_only" or (
            w.seed.policy == "hints_first" and k == 0
        )
        kind = "no_source" if pair is None else "hint" if hint else "answer"
        reply = Message(
            id=new_id(),
            author="tutor",
            kind=kind,
            text=pair["answer"] if pair else no_source_text(self.settings),
            hint_number=hints + 1 if kind == "hint" else None,
            created_at=at,
            **common,
        )
        self.session.add(reply)
        if pair:
            self.session.add(_cite(topic, message_id=reply.id))
        if kind == "answer":
            w.seed.answers.append(reply)
        self._log(
            w,
            at,
            kind="chat",
            question=text,
            fragment_ids=[topic.fragment.id] if pair else [],
            outcome=kind,
            answer=reply.text,
        )
        return at, hints + 1 if kind == "hint" else 0

    def exercises(self, w: Window, struggling: bool) -> None:
        b = w.behaviour
        for n in range(w.rng.between(b.exercises), 0, -1):
            # Half of a struggling student's exercises are recent, so the error rate
            # shows.
            at = w.when(recent=struggling and n % 2 == 0)
            topic = w.topic_at(at)
            exercise = w.rng.choice(topic.content["exercises"])
            roll = w.rng.random()
            verdict = (
                "correct"
                if roll < b.correct
                else "partially_correct"
                if roll < b.correct + b.partial
                else "incorrect"
            )
            mistake = verdict != "correct"
            submission = ExerciseSubmission(
                id=new_id(),
                course_id=w.seed.course.id,
                student_id=w.student.id,
                problem_statement=exercise["statement"],
                worked_answer=exercise["wrong_answer" if mistake else "correct_answer"],
                verdict=verdict,
                mistake_location=exercise["mistake_location"] if mistake else None,
                error_type=exercise["error_type"] if mistake else None,
                topic_id=topic.topic.id,
                topic_name=topic.topic.name,
                explanation=exercise["explanation"]
                if mistake
                else w.rng.choice(PRAISE),
                explanation_kind="answer",
                saved_to_record=mistake,
                is_stub=False,
                created_at=at,
            )
            self.session.add(submission)
            self.session.add(_cite(topic, submission_id=submission.id))
            if mistake:
                self.session.add(
                    LearningRecordEntry(
                        id=new_id(),
                        course_id=w.seed.course.id,
                        student_id=w.student.id,
                        submission_id=submission.id,
                        error_type=exercise["error_type"],
                        topic_id=topic.topic.id,
                        topic_name=topic.topic.name,
                        created_at=at,
                    )
                )
            if verdict == "incorrect":
                w.seed.mistakes.append(submission)
            self._log(
                w,
                at,
                kind="exercise",
                question=exercise["statement"],
                fragment_ids=[topic.fragment.id],
                outcome=verdict,
                answer=submission.explanation,
            )

    def quizzes(self, w: Window) -> None:
        for _ in range(w.rng.between(w.behaviour.quizzes)):
            at = w.when()
            topic = w.topic_at(at, reviewed_only=True)
            questions = w.seed.approved[topic.topic.id]
            quiz = Quiz(
                id=new_id(),
                course_id=w.seed.course.id,
                student_id=w.student.id,
                topic_id=topic.topic.id,
                topic_name=topic.topic.name,
                status="completed",
                question_count=len(questions),
                level=questions[0].difficulty,
                streak=0,
                start_basis={
                    "reason": "no_score",
                    "mastery_level": None,
                    "score": None,
                },
                started_at=at,
            )
            self.session.add(quiz)
            for position, question in enumerate(questions, start=1):
                at += timedelta(seconds=30 + w.rng.random() * 60)
                right = w.rng.chance(w.behaviour.quiz_right)
                wrong = (question.correct_option + 1 + w.rng.randint(0, 2)) % len(
                    question.options
                )
                self.session.add(
                    QuizItem(
                        id=new_id(),
                        quiz_id=quiz.id,
                        question_id=question.id,
                        position=position,
                        topic_id=topic.topic.id,
                        topic_name=topic.topic.name,
                        statement=question.statement,
                        options=list(question.options),
                        correct_option=question.correct_option,
                        explanation=question.explanation,
                        difficulty=question.difficulty,
                        choice=question.correct_option if right else wrong,
                        correct=right,
                        answered_at=at,
                    )
                )
                quiz.level = question.difficulty
                quiz.streak = run(quiz.streak, right)
            quiz.completed_at = at

    def test_attempts(self, w: Window, lucas: bool) -> None:
        """Most students took the pre-test; some already the post-test."""
        for phase, row in w.seed.phases.items():
            skip = (
                (lucas or not w.rng.chance(0.4))
                if phase == "post"
                else not w.rng.chance(0.9)
            )
            if skip or row.opened_at is None:
                continue
            offset = w.rng.random() * 6 * DAY
            submitted = w.during(min(self.now - DAY, row.opened_at + offset))
            odds = w.behaviour.quiz_right - (0.2 if phase == "pre" else 0)
            attempt = TestAttempt(
                id=new_id(),
                course_id=w.seed.course.id,
                student_id=w.student.id,
                phase=phase,
                submitted_at=max(row.opened_at + timedelta(hours=1), submitted),
            )
            self.session.add(attempt)
            for question in w.seed.test_questions:
                right = w.rng.chance(odds)
                self.session.add(
                    TestAnswer(
                        attempt_id=attempt.id,
                        question_id=question.id,
                        choice=question.correct_option
                        if right
                        else (question.correct_option + 2) % 4,
                        correct=right,
                    )
                )

    # --- Teachers ------------------------------------------------------------------

    def flags(self, seed: CourseSeed) -> None:
        """The teacher's corrections of a few tutor answers and exercise feedback."""
        rng = Rng(f"flags:{seed.key}")
        answers, mistakes = list(seed.answers), list(seed.mistakes)
        for n, (category, text) in enumerate(CORRECTIONS):
            pool = mistakes if category == "incorrect" else answers
            if not pool:
                continue
            target = pool.pop(rng.randrange(len(pool)))
            created = min(
                self.now - timedelta(hours=1),
                target.created_at + (n + 1) * timedelta(hours=1),
            )
            is_message = isinstance(target, Message)
            self.session.add(
                TeacherFlag(
                    id=new_id(),
                    course_id=seed.course.id,
                    message_id=target.id if is_message else None,
                    submission_id=None if is_message else target.id,
                    category=category,
                    correction=text,
                    author_id=seed.teacher.id,
                    created_at=created,
                    updated_at=created,
                )
            )

    def tag(self, user: Profile, name: str, color: str) -> CourseTag:
        tag = self.session.scalar(
            select(CourseTag).where(
                CourseTag.user_id == user.id, CourseTag.name == name
            )
        )
        if tag is None:
            tag = CourseTag(id=new_id(), user_id=user.id, name=name, color=color)
            self.session.add(tag)
            self.session.flush()
        return tag

    def tags_and_favorites(
        self, courses: dict[str, CourseSeed], users: dict[str, Profile]
    ) -> None:
        """Each teacher tags their courses by class group; some courses are starred."""
        groups = {g["key"]: g for g in people()["groups"]}
        for meta in people()["courses"]:
            seed = courses[meta["key"]]
            group = groups[meta["group"]]
            tag = self.tag(seed.teacher, group["label"], group["tag_color"])
            self.session.add(CourseTagLink(tag_id=tag.id, course_id=seed.course.id))
        for email, keys in FAVORITES.items():
            for key in keys:
                self.session.add(
                    CourseFavorite(
                        user_id=users[email].id, course_id=courses[key].course.id
                    )
                )
        review = self.tag(users[LUCAS], "Repasar", "amber")
        for key in ("algebra-3b", "lengua-3b"):
            self.session.add(
                CourseTagLink(tag_id=review.id, course_id=courses[key].course.id)
            )
        self.session.commit()
