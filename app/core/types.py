"""Value sets of the text columns the database constrains (supabase/migrations).

`app.models` types its columns with them and `app.schemas` its fields, so pyright checks
a value against both. The columns stay plain text: these aliases type them and never
change how SQLAlchemy reads or writes them.
"""

from typing import Literal

# profiles
Role = Literal["admin", "teacher", "student"]
AccountStatus = Literal["active", "disabled"]
Language = Literal["es", "en"]

# enrolments, course_tags
EnrolmentStatus = Literal["active", "revoked"]
TagColor = Literal["violet", "green", "blue", "amber", "red", "gray"]

# tutor_settings
TutorLevel = Literal["basic", "intermediate", "advanced"]
Tone = Literal["friendly", "neutral", "formal"]
SolutionPolicy = Literal["direct", "hints_first", "hints_only"]

# documents, topic_assignments
FileType = Literal["pdf", "docx", "markdown"]
ProcessingStatus = Literal["processing", "ready", "error"]
ValidationStatus = Literal["pending_validation", "validated", "excluded"]
ErrorReason = Literal[
    "unsupported_format",
    "no_readable_text",
    "processing_failed",
    "processing_interrupted",
]
AssignmentStatus = Literal["suggested", "confirmed"]

# messages
MessageAuthor = Literal["student", "tutor"]
MessageKind = Literal["question", "answer", "hint", "no_source"]
MessageStatus = Literal["sent", "failed"]

# exercise_submissions, mistake_reviews, teacher_flags
Verdict = Literal["correct", "partially_correct", "incorrect", "not_assessed"]
# Whether an explanation was grounded in the material or found none.
ExplanationKind = Literal["answer", "no_source"]
FlagCategory = Literal["incorrect", "poor"]

# quiz_questions, quizzes
QuestionStatus = Literal["pending", "approved", "rejected"]
QuestionOrigin = Literal["ai", "edited"]
QuizStatus = Literal["in_progress", "completed"]

# test_phases, test_attempts
Phase = Literal["pre", "post"]
PhaseStatus = Literal["not_open", "open", "closed"]

# llm_credentials, consent_events, questionnaires
CredentialProvider = Literal["openai", "anthropic", "openai_compatible"]
ConsentAction = Literal["given", "revoked"]
Audience = Literal["student", "teacher"]
QuestionnaireStatus = Literal["open", "closed"]
