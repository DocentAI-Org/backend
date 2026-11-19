"""ORM mappings of the tables owned by supabase/migrations (no create_all)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.types import (
    AccountStatus,
    AssignmentStatus,
    Audience,
    ConsentAction,
    CredentialProvider,
    EnrolmentStatus,
    ErrorReason,
    ExplanationKind,
    FileType,
    FlagCategory,
    InteractionKind,
    Language,
    MessageAuthor,
    MessageKind,
    MessageStatus,
    Outcome,
    Period,
    Phase,
    PhaseStatus,
    ProcessingStatus,
    QuestionnaireStatus,
    QuestionOrigin,
    QuestionStatus,
    QuizStatus,
    Role,
    SolutionPolicy,
    TagColor,
    Tone,
    TutorLevel,
    ValidationStatus,
    Verdict,
)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    role: Mapped[Role] = mapped_column(String, server_default="student")
    display_name: Mapped[str]
    email: Mapped[str | None]
    pseudonym_code: Mapped[str | None]
    status: Mapped[AccountStatus] = mapped_column(String, server_default="active")
    preferred_language: Mapped[Language] = mapped_column(String, server_default="es")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    name: Mapped[str]
    description: Mapped[str | None]
    class_code: Mapped[str]
    class_code_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    teacher: Mapped[Profile] = relationship(lazy="joined")


class Enrolment(Base):
    __tablename__ = "enrolments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    status: Mapped[EnrolmentStatus] = mapped_column(String, server_default="active")
    joined_at: Mapped[datetime] = mapped_column(server_default=func.now())
    disclosure_acknowledged_at: Mapped[datetime | None]

    course: Mapped[Course] = relationship(lazy="joined")
    student: Mapped[Profile] = relationship(lazy="joined")


class CourseFavorite(Base):
    """A course a teacher or student starred (specs/016); listed first."""

    __tablename__ = "course_favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id"), primary_key=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CourseTag(Base):
    """A user's own tag for their courses (specs/016 US4)."""

    __tablename__ = "course_tags"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    name: Mapped[str]
    color: Mapped[TagColor] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CourseTagLink(Base):
    __tablename__ = "course_tag_links"

    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_tags.id"), primary_key=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), primary_key=True
    )


class TutorSettings(Base):
    __tablename__ = "tutor_settings"

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), primary_key=True
    )
    level: Mapped[TutorLevel] = mapped_column(String, server_default="intermediate")
    tone: Mapped[Tone] = mapped_column(String, server_default="friendly")
    solution_policy: Mapped[SolutionPolicy] = mapped_column(
        String, server_default="hints_first"
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    file_name: Mapped[str]
    file_type: Mapped[FileType] = mapped_column(String)
    size_bytes: Mapped[int]
    storage_path: Mapped[str]
    page_count: Mapped[int | None]
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        String, server_default="processing"
    )
    error_reason: Mapped[ErrorReason | None] = mapped_column(String)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        String, server_default="pending_validation"
    )
    validated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    validated_at: Mapped[datetime | None]
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())

    validator: Mapped[Profile | None] = relationship(
        foreign_keys=[validated_by], lazy="joined"
    )


class Fragment(Base):
    __tablename__ = "fragments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    position: Mapped[int]
    section: Mapped[str]
    location_label: Mapped[str]
    text: Mapped[str] = mapped_column(Text)
    excluded: Mapped[bool] = mapped_column(server_default="false")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))

    document: Mapped[Document] = relationship()


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    name: Mapped[str]
    position: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TopicAssignment(Base):
    __tablename__ = "topic_assignments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    section: Mapped[str | None]
    status: Mapped[AssignmentStatus] = mapped_column(String, server_default="confirmed")
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    confirmed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    topic: Mapped[Topic] = relationship(lazy="joined")
    document: Mapped[Document] = relationship(lazy="joined")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_message_at: Mapped[datetime] = mapped_column(server_default=func.now())

    student: Mapped[Profile] = relationship(lazy="joined")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    author: Mapped[MessageAuthor] = mapped_column(String)
    kind: Mapped[MessageKind] = mapped_column(String)
    status: Mapped[MessageStatus] = mapped_column(String, server_default="sent")
    text: Mapped[str] = mapped_column(Text)
    request_solution: Mapped[bool] = mapped_column(server_default="false")
    hint_number: Mapped[int | None]
    counts_toward_limit: Mapped[bool] = mapped_column(server_default="false")
    # {error_type, count, window_days} when the answer was adapted (specs/013).
    adaptation: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())

    citations: Mapped[list["Citation"]] = relationship(
        order_by="Citation.position", lazy="selectin"
    )
    flag: Mapped["TeacherFlag | None"] = relationship(lazy="selectin")


class ExerciseSubmission(Base):
    __tablename__ = "exercise_submissions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    problem_statement: Mapped[str] = mapped_column(Text)
    worked_answer: Mapped[str] = mapped_column(Text)
    verdict: Mapped[Verdict] = mapped_column(String)
    mistake_location: Mapped[str | None]
    error_type: Mapped[str | None]
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"))
    topic_name: Mapped[str | None]
    explanation: Mapped[str] = mapped_column(Text)
    explanation_kind: Mapped[ExplanationKind] = mapped_column(String)
    saved_to_record: Mapped[bool] = mapped_column(server_default="false")
    is_stub: Mapped[bool] = mapped_column(server_default="false")
    adaptation: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())

    student: Mapped[Profile] = relationship(lazy="joined")
    citations: Mapped[list["Citation"]] = relationship(
        order_by="Citation.position", lazy="selectin"
    )
    flag: Mapped["TeacherFlag | None"] = relationship(lazy="selectin")


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exercise_submissions.id")
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quiz_questions.id")
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mistake_reviews.id")
    )
    fragment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fragments.id"))
    document_name: Mapped[str]
    location_label: Mapped[str]
    position: Mapped[int]

    fragment: Mapped[Fragment | None] = relationship(lazy="selectin")


class MistakeReview(Base):
    """A targeted review of a repeated mistake (specs/005), one per submission."""

    __tablename__ = "mistake_reviews"

    id: Mapped[uuid.UUID] = _uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exercise_submissions.id")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    error_type: Mapped[str]
    topic_name: Mapped[str | None]
    kind: Mapped[ExplanationKind] = mapped_column(String)
    explanation: Mapped[str] = mapped_column(Text)
    worked_example: Mapped[str | None] = mapped_column(Text)
    practice: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())

    citations: Mapped[list["Citation"]] = relationship(
        order_by="Citation.position", lazy="selectin"
    )


class QuizQuestion(Base):
    """A multiple-choice question drafted by the AI, reviewed by the teacher (006)."""

    __tablename__ = "quiz_questions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id"))
    statement: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(ARRAY(Text))
    correct_option: Mapped[int] = mapped_column(SmallInteger)
    explanation: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[QuestionStatus] = mapped_column(String, server_default="pending")
    origin: Mapped[QuestionOrigin] = mapped_column(String, server_default="ai")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    reviewed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())

    topic: Mapped[Topic] = relationship(lazy="joined")
    citations: Mapped[list["Citation"]] = relationship(
        order_by="Citation.position", lazy="selectin"
    )


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"))
    topic_name: Mapped[str | None]
    status: Mapped[QuizStatus] = mapped_column(String, server_default="in_progress")
    question_count: Mapped[int] = mapped_column(SmallInteger)
    level: Mapped[int] = mapped_column(SmallInteger)
    streak: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    # Why it started at its level (specs/021); null for quizzes started before.
    start_basis: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    started_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    completed_at: Mapped[datetime | None]

    items: Mapped[list["QuizItem"]] = relationship(
        order_by="QuizItem.position", lazy="selectin"
    )


class QuizItem(Base):
    """A question as the student saw it, and their answer (snapshot, FR-005)."""

    __tablename__ = "quiz_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    quiz_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quizzes.id"))
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quiz_questions.id")
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"))
    topic_name: Mapped[str]
    statement: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(ARRAY(Text))
    correct_option: Mapped[int] = mapped_column(SmallInteger)
    explanation: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger)
    choice: Mapped[int | None] = mapped_column(SmallInteger)
    correct: Mapped[bool | None]
    answered_at: Mapped[datetime | None]

    question: Mapped[QuizQuestion | None] = relationship(lazy="selectin")


class TestQuestion(Base):
    """A pre/post-test question (specs/008), frozen once the pre-test is opened."""

    __tablename__ = "test_questions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"))
    topic_name: Mapped[str]
    position: Mapped[int]
    statement: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(ARRAY(Text))
    correct_option: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class TestPhase(Base):
    __tablename__ = "test_phases"

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), primary_key=True
    )
    phase: Mapped[Phase] = mapped_column(String, primary_key=True)
    status: Mapped[PhaseStatus] = mapped_column(String, server_default="not_open")
    opened_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    phase: Mapped[Phase] = mapped_column(String)
    submitted_at: Mapped[datetime] = mapped_column(
        server_default=func.clock_timestamp()
    )

    answers: Mapped[list["TestAnswer"]] = relationship(lazy="selectin")


class TestAnswer(Base):
    __tablename__ = "test_answers"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_attempts.id"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_questions.id"), primary_key=True
    )
    choice: Mapped[int] = mapped_column(SmallInteger)
    correct: Mapped[bool]


class LearningRecordEntry(Base):
    __tablename__ = "learning_record_entries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exercise_submissions.id")
    )
    error_type: Mapped[str]
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id"))
    topic_name: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class ErrorType(Base):
    """The error taxonomy (specs/003): data, so the educational stream can change it."""

    __tablename__ = "error_types"

    code: Mapped[str] = mapped_column(primary_key=True)
    position: Mapped[int]
    label_es: Mapped[str]
    label_en: Mapped[str]
    description_es: Mapped[str] = mapped_column(Text)
    description_en: Mapped[str] = mapped_column(Text)
    provisional: Mapped[bool]


class PedagogyCriteria(Base):
    """Study defaults (no course) or a course's overrides, per group (specs/015)."""

    __tablename__ = "pedagogy_criteria"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id"))
    inactive: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    error_rate: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    repeated_mistakes: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    adaptation: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    mastery: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    quiz: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    provisional: Mapped[bool] = mapped_column(server_default="true")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))


class AISettings(Base):
    """The study's AI settings (no course) or a course's, per group (specs/019)."""

    __tablename__ = "ai_settings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id"))
    models: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    limits: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    retrieval: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    ceiling: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    instructions: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    allow_teacher_keys: Mapped[bool] = mapped_column(server_default="false")
    notices: Mapped[list] = mapped_column(JSONB, server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))


class AITest(Base):
    """A teacher's test message (specs/019), kept to limit them to 20 an hour."""

    __tablename__ = "ai_tests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    task: Mapped[str]
    model: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LLMCredential(Base):
    """A key for a commercial model: the study's (no course) or a teacher's
    (specs/019)."""

    __tablename__ = "llm_credentials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("courses.id"))
    provider: Mapped[CredentialProvider] = mapped_column(String)
    label: Mapped[str]
    base_url: Mapped[str | None]
    encrypted_key: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str]
    offered_models: Mapped[list | None] = mapped_column(JSONB(none_as_null=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TeacherFlag(Base):
    __tablename__ = "teacher_flags"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exercise_submissions.id")
    )
    category: Mapped[FlagCategory] = mapped_column(String)
    correction: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.clock_timestamp(), onupdate=func.clock_timestamp()
    )

    author: Mapped[Profile | None] = relationship(lazy="joined")


class InteractionLog(Base):
    __tablename__ = "interaction_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id"))
    # None only for teacher actions such as generating quiz questions (specs/006).
    student_ref: Mapped[str | None]
    kind: Mapped[InteractionKind] = mapped_column(String)
    question: Mapped[str] = mapped_column(Text)
    retrieved_fragment_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid))
    answer: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None]
    input_tokens: Mapped[int] = mapped_column(server_default="0")
    output_tokens: Mapped[int] = mapped_column(server_default="0")
    latency_ms: Mapped[int] = mapped_column(server_default="0")
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), server_default="0"
    )
    outcome: Mapped[Outcome] = mapped_column(String)
    error_code: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DailyUsage(Base):
    __tablename__ = "daily_usage"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id"), primary_key=True
    )
    usage_date: Mapped[date] = mapped_column(primary_key=True)
    used: Mapped[int] = mapped_column(server_default="0")


class CourseUsage(Base):
    """Messages a student used in a course in a period (specs/019)."""

    __tablename__ = "course_usage"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id"), primary_key=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id"), primary_key=True
    )
    period: Mapped[Period] = mapped_column(String, primary_key=True)
    period_start: Mapped[date] = mapped_column(primary_key=True)
    used: Mapped[int] = mapped_column(server_default="0")


class ConsentEvent(Base):
    __tablename__ = "consent_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    action: Mapped[ConsentAction] = mapped_column(String)
    version: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class Questionnaire(Base):
    """A study questionnaire in an external tool (specs/012)."""

    __tablename__ = "questionnaires"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str]
    url: Mapped[str]
    audience: Mapped[Audience] = mapped_column(String)
    status: Mapped[QuestionnaireStatus] = mapped_column(String, server_default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
