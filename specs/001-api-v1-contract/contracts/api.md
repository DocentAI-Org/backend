# API Contract: DocentAI API v1

**Feature**: [spec.md](../spec.md) · **Data model**: [data-model.md](../data-model.md)

The normative contract is the generated `openapi.json` at the repository root (constitution III).
This document is its design: every endpoint, its role, models and error codes. Field names are
`snake_case` in JSON. All endpoints except `GET /v1/health` require `Authorization: Bearer <JWT>`.

## Conventions

- **Pagination**: list endpoints accept `limit` (1–100, default 20) and `offset` (≥ 0) and return
  `Page[T] = {items: T[], total: int, limit: int, offset: int}`.
- **Errors**: `{"error": {"code": str, "message": str, "details": object | null}}`.
- **Stubs**: endpoints marked *stub* have `x-stub: true` in OpenAPI (none since specs/003).
- **Not found vs forbidden**: another user's resource → `404 not_found`; wrong role for a router →
  `403 forbidden`.

## Error codes

| HTTP | code | When |
|---|---|---|
| 401 | `unauthenticated` | missing, invalid or expired token |
| 403 | `forbidden` | role not allowed for the router, or account disabled |
| 404 | `not_found` | resource missing or not visible to the caller |
| 422 | `validation_error` | request body/query invalid (`details.fields`) |
| 409 | `conflict` | generic state conflict |
| 400 | `class_code_invalid` | unknown or superseded code |
| 400 | `class_code_disabled` | code exists but is disabled |
| 403 | `enrolment_revoked` | student's enrolment in the course was revoked |
| 415 | `unsupported_file_type` | not PDF, DOCX or Markdown |
| 413 | `file_too_large` | over `MAX_UPLOAD_MB` |
| 409 | `document_not_ready` | validate/exclude a document that is not `ready` |
| 409 | `topic_name_taken` | duplicate topic name in the course |
| 409 | `disclosure_not_acknowledged` | student messages before acknowledging the AI disclosure |
| 429 | `daily_limit_reached` | `details.resets_at` |
| 409 | `solution_not_allowed` | `request_solution` with policy `hints_only` |
| 503 | `tutor_unavailable` | model provider failed or timed out; `details.message_id` |
| 400 | `not_a_tutor_message` | flag target is not a tutor message |
| 409 | `email_taken` | admin creates an account whose email already exists |
| 503 | `auth_unavailable` | Supabase Auth admin API unreachable or failing |
| 503 | `storage_unavailable` | Supabase Storage unreachable or failing |
| 409 | `no_questions` | quiz started with no approved question (for that topic) (specs/006) |
| 409 | `not_current_question` | quiz answer for a question that is not the current one |
| 409 | `quiz_completed` | quiz answer after the last question |

## Public / self

| Method | Path | Role | Request | Response |
|---|---|---|---|---|
| GET | `/v1/health` | public | — | `Health {status, service, version, database: ok\|error, llm: ok\|error}` |
| GET | `/v1/me` | any | — | `Me {id, role, display_name, email?, is_pseudonymous, preferred_language}` |
| PATCH | `/v1/me` | any | `MeUpdate {preferred_language}` | `Me` |

## Admin (`/v1/admin`, role admin)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/users?role=&status=` | — | `Page[AdminUser {id, role, display_name, email?, is_pseudonymous, status, created_at}]` |
| POST | `/teachers` | `TeacherCreate {email, display_name, password?}` | 201 `CreatedAccount {user: AdminUser, initial_password}` |
| POST | `/students/pseudonymous` | `PseudonymousBatchCreate {count 1–100}` | 201 `PseudonymousBatch {accounts: [{user_id, code, initial_password}]}` |
| GET | `/courses` | — | `Page[AdminCourse {id, name, teacher_name, student_count, created_at}]` |
| GET | `/evaluation-set` | — | `Page[EvaluationItem {flag_id, course_id, category, correction, question, original_answer, citations, created_at}]` |

`initial_password` is returned once and never stored in plain text by the API.

## Teacher (`/v1/teacher`, role teacher, own courses only)

### Courses and enrolment (T1)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/courses` | `CourseCreate {name, description?}` | 201 `TeacherCourse` |
| GET | `/courses` | — | `Page[TeacherCourse]` |
| GET | `/courses/{course_id}` | — | `TeacherCourse` |
| PATCH | `/courses/{course_id}` | `CourseUpdate {name?, description?}` | `TeacherCourse` |
| POST | `/courses/{course_id}/class-code/regenerate` | — | `TeacherCourse` |
| PATCH | `/courses/{course_id}/class-code` | `ClassCodeUpdate {active}` | `TeacherCourse` |
| GET | `/courses/{course_id}/students` | — | `Page[CourseStudent {student_id, display_name, joined_at, status}]` |
| DELETE | `/courses/{course_id}/students/{student_id}` | — | 204 (revokes) |

`TeacherCourse {id, name, description?, class_code, class_code_active, invitation_path,
student_count, created_at}`. `invitation_path` is `/join/<class_code>` (`/unirse/<class_code>` before the app's English routes); the frontend prefixes its
own origin.

### Tutor settings (T3)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/courses/{course_id}/tutor-settings` | — | `TutorSettings {level, tone, solution_policy, updated_at}` |
| PUT | `/courses/{course_id}/tutor-settings` | `TutorSettingsUpdate {level, tone, solution_policy}` | `TutorSettings` |

### Material (T2)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/courses/{course_id}/documents` | multipart `file` | 202 `Document` |
| GET | `/courses/{course_id}/documents` | — | `Page[Document]` |
| GET | `/courses/{course_id}/documents/{document_id}` | — | `Document` |
| DELETE | `/courses/{course_id}/documents/{document_id}` | — | 204 |
| POST | `/courses/{course_id}/documents/{document_id}/validate` | — | `Document` |
| POST | `/courses/{course_id}/documents/{document_id}/exclude` | — | `Document` |
| GET | `/courses/{course_id}/documents/{document_id}/fragments` | — | `Page[Fragment {id, position, section, location_label, text, excluded}]` |
| PATCH | `/courses/{course_id}/documents/{document_id}/fragments/{fragment_id}` | `FragmentUpdate {excluded}` | `Fragment` |
| GET | `/courses/{course_id}/documents/{document_id}/file-url` | — | `SignedUrl {url, expires_at}` |

`Document {id, file_name, file_type, size_bytes, page_count?, processing_status, error_reason?,
validation_status, validated_by_name?, validated_at?, fragment_count, excluded_fragment_count,
uploaded_at, topics: [TopicRef {id, name}]}`.

### Topics (T9)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/courses/{course_id}/topics` | — | `list[Topic {id, name, position, assignment_count}]` |
| POST | `/courses/{course_id}/topics` | `TopicCreate {name}` | 201 `Topic` |
| PATCH | `/courses/{course_id}/topics/{topic_id}` | `TopicUpdate {name}` | `Topic` |
| DELETE | `/courses/{course_id}/topics/{topic_id}` | — | 204 |
| PUT | `/courses/{course_id}/topics/order` | `TopicOrder {topic_ids}` | `list[Topic]` |
| GET | `/courses/{course_id}/topic-assignments?status=` | — | `list[TopicAssignment {id, topic_id, topic_name, document_id, document_name, section?, status}]` |
| POST | `/courses/{course_id}/topic-assignments` | `TopicAssignmentCreate {topic_id, document_id, section?}` | 201 `TopicAssignment` (confirmed) |
| PATCH | `/courses/{course_id}/topic-assignments/{assignment_id}` | `TopicAssignmentUpdate {topic_id?, status: confirmed}` | `TopicAssignment` |
| DELETE | `/courses/{course_id}/topic-assignments/{assignment_id}` | — | 204 |
| GET | `/courses/{course_id}/unassigned-material` | — | `list[UnassignedDocument {document_id, document_name, sections: [str]}]` |

### Review and corrections (T4, T6)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/courses/{course_id}/conversations?student_id=&from=&to=&has_no_source=` | — | `Page[ConversationSummary {id, student_id, student_name, started_at, last_message_at, message_count, has_no_source}]` |
| GET | `/courses/{course_id}/conversations/{conversation_id}` | — | `TeacherConversation {…summary, messages: [TeacherMessage]}` |
| GET | `/courses/{course_id}/submissions?student_id=&from=&to=` | — | `Page[TeacherSubmission]` |
| GET | `/courses/{course_id}/submissions/{submission_id}` | — | `TeacherSubmission` |
| PUT | `/courses/{course_id}/messages/{message_id}/flag` | `FlagUpsert {category, correction}` | `TeacherFlag {id, category, correction, author_name, created_at, updated_at}` |
| DELETE | `/courses/{course_id}/messages/{message_id}/flag` | — | 204 |
| PUT | `/courses/{course_id}/submissions/{submission_id}/flag` | `FlagUpsert` | `TeacherFlag` |
| DELETE | `/courses/{course_id}/submissions/{submission_id}/flag` | — | 204 |
| GET | `/courses/{course_id}/students/{student_id}/learning-record` | — | `Page[LearningRecordEntry]` |

`TeacherMessage` = `StudentMessage` fields + `flag: TeacherFlag?`.

### Dashboard and at-risk students (T5, T8; specs/004)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/courses/{course_id}/dashboard?period=7d\|30d\|all` (default `30d`) | — | `TeacherDashboard` |
| GET | `/courses/{course_id}/students/{student_id}/risk` | — | `StudentRisk` |
| GET | `/risk-criteria` | — | `RiskCriteriaList {provisional, items: [{code, enabled, thresholds}]}` |
| GET | `/courses/{course_id}/students/{student_id}/progress` (specs/007) | — | `Progress`, identical to the student's |

- `TeacherDashboard {period, since?, activity: {messages, exercises}, enough_data, thresholds:
  {messages, exercises}, errors_by_topic: [{topic_id?, topic_name?, topic_deleted, errors,
  students, top_error_type}], errors_by_student: [{student_id, display_name, errors,
  top_error_type, top_topic_name?}], at_risk: [{student_id, display_name, last_activity_at?,
  reasons: [RiskReason]}], criteria_provisional}`; active students only; `at_risk` does not depend
  on `period`.
- `RiskReason` (discriminated by `criterion`): `{criterion: "inactive", days_inactive,
  threshold_days, since, never_active}` | `{criterion: "error_rate", mistakes, assessed,
  window_days, min_exercises, threshold_rate}`; thresholds are those applied to the course.
- `StudentRisk {student_id, display_name, at_risk, reasons, last_activity_at?, weekly_activity:
  [{week_start (Monday, UTC), messages, exercises, quizzes (completed, specs/007)}] (8 weeks, oldest first), criteria_provisional}`;
  a revoked student is never at risk.

### Quiz questions (T7; specs/006)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/courses/{course_id}/topics/{topic_id}/questions/generate` | `GenerateQuestions {count 1–10 = 5}` | 201 `GeneratedQuestions {kind: answer\|no_source, questions: [TeacherQuestion]}`; 503 `tutor_unavailable` |
| GET | `/courses/{course_id}/questions?status&topic_id` | — | `QuestionPage` = `Page[TeacherQuestion]` + `counts {pending, approved, rejected}` |
| PATCH | `/courses/{course_id}/questions/{question_id}` | `QuestionUpdate {statement?, options? (4 distinct), correct_option? 0–3, explanation?, difficulty? 1–3, status?}` | `TeacherQuestion` |

- `TeacherQuestion {id, topic_id, topic_name, statement, options: [4], correct_option,
  explanation, difficulty: 1|2|3, status: pending|approved|rejected, origin: ai|edited,
  citations, answered_count, correct_rate?, reviewed_at?, created_at}`.
- Drafts come from the topic's confirmed material (or the material closest to its name), are
  stored `pending`, and are logged as interactions of kind `quiz_generation` with no student
  reference; nothing is charged to students.

## Student (`/v1/student`, role student, own data in enrolled courses only)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/enrolments` | `JoinCourse {class_code}` | 200 `StudentCourse` |
| GET | `/courses` | — | `Page[StudentCourse {id, name, description?, teacher_name, joined_at, disclosure_acknowledged}]` |
| GET | `/courses/{course_id}` | — | `StudentCourse` |
| GET | `/courses/{course_id}/tutor-settings` | — | `StudentTutorSettings {level, tone, solution_policy}` |
| POST | `/courses/{course_id}/disclosure` | — | `StudentCourse` (acknowledged) |
| GET | `/allowance` | — | `Allowance {limit, used, remaining, resets_at}` |
| POST | `/courses/{course_id}/conversations` | — | 201 `Conversation {id, started_at, last_message_at, messages: []}` |
| GET | `/courses/{course_id}/conversations` | — | `Page[StudentConversationSummary {id, started_at, last_message_at, preview}]` |
| GET | `/courses/{course_id}/conversations/{conversation_id}` | — | `Conversation` |
| POST | `/courses/{course_id}/conversations/{conversation_id}/messages` | `MessageCreate {text 1–4000, request_solution=false}` | 201 `TutorExchange {student_message, tutor_message, allowance}` |
| POST | `/courses/{course_id}/conversations/{conversation_id}/messages/{message_id}/retry` | — | 201 `TutorExchange` |
| POST | `/courses/{course_id}/submissions` (real feedback since specs/003; 503 `tutor_unavailable`) | `SubmissionCreate {problem_statement, worked_answer}` | 201 `StudentSubmission` |
| GET | `/courses/{course_id}/submissions` | — | `Page[StudentSubmission]` |
| GET | `/courses/{course_id}/submissions/{submission_id}` | — | `StudentSubmission` |
| GET | `/courses/{course_id}/learning-record` | — | `Page[LearningRecordEntry]` |
| GET | `/courses/{course_id}/progress` (specs/007) | — | `Progress` |
| GET | `/courses/{course_id}/quiz-topics` | — | `[QuizTopic {topic_id, topic_name, question_count}]` (topics with approved questions) |
| POST | `/courses/{course_id}/quizzes` (specs/006; 409 `consent_required`, `no_questions`) | `QuizStart {topic_id?}` | 201 `Quiz` |
| GET | `/courses/{course_id}/quizzes` | — | `Page[Quiz]` |
| GET | `/courses/{course_id}/quizzes/{quiz_id}` | — | `QuizDetail` = `Quiz` + `items: [AnsweredItem]` |
| POST | `/courses/{course_id}/quizzes/{quiz_id}/answers` | `QuizAnswer {question_id, choice 0–3}` | `AnswerResult {correct, correct_option, explanation, citations, difficulty_change?, quiz: Quiz}` |

Shared models:

- `StudentMessage {id, author: student|tutor, kind: question|answer|hint|no_source, status:
  sent|failed, text, hint_number?, request_solution, counts_toward_limit, created_at, citations:
  [Citation], correction: Correction?}`
- `Citation {fragment_id?, document_name, location_label, passage?, available}`
- `Correction {text, reviewed_at}` (no category — FR-092)
- `StudentSubmission {id, problem_statement, worked_answer, verdict: correct|partially_correct|
  incorrect|not_assessed, mistake_location?, error_type? (code from `GET /v1/error-types`),
  topic_name?, explanation, explanation_kind, citations, saved_to_record, is_stub (always false
  since specs/003; to be removed), correction?, created_at}`
- `ErrorTaxonomy {provisional, items: [{code, label: {es, en}, description: {es, en}}]}` at
  `GET /v1/error-types` (any signed-in user; specs/003)
- `StudentSubmission.repeated_mistake? {count, window_days, error_type, topic_name?}`: set when
  the mistake is the Nth of the same type and topic within the window, counted up to this
  submission (specs/005; provisional `REPEATED_MISTAKE_COUNT=3`, `REPEATED_MISTAKE_DAYS=30`)
- `MistakeReview {id, submission_id, error_type, topic_name?, kind: answer|no_source,
  explanation, worked_example?, practice: [str], citations, created_at}`:
  `POST /v1/student/courses/{course_id}/submissions/{submission_id}/review` (201 created and
  counted; 200 if it existed, free; 409 `no_repeated_mistake`; 429; 503 `tutor_unavailable`),
  `GET` on the same path, and `GET /v1/teacher/courses/{course_id}/submissions/{submission_id}/review`
- `TeacherSubmission` = `StudentSubmission` + `student_id, student_name, flag?`
- `Progress {provisional, criteria {window, min_items, progressing, mastered}, updated_at?,
  quizzes_completed, topics: [TopicProgress] (every course topic, in order), unassigned?}`;
  `TopicProgress {topic_id?, topic_name?, level: not_started|insufficient|starting|progressing|
  mastered, score? (0–1, latest `window` graded items: exercise 1/½/0, quiz answer 1/0), basis
  {exercises_correct, exercises_partial, exercises_total, quiz_right, quiz_total} (the items in
  the window), history: [{week_start, score?}] (8 weeks), top_errors: [{error_type, count,
  latest_submission_id}] (≤ 3), last_activity_at?}` (provisional `PROGRESS_*` settings).
  Since specs/007, correct exercises also carry their `topic_name`.
- `Quiz {id, topic_id?, topic_name?, status: in_progress|completed, question_count,
  answered_count, level: 1|2|3, current?: {id (question), position, statement, options,
  difficulty, topic_name}, summary?: {score, total, final_level, by_topic: [{topic_id?,
  topic_name, correct, total}]}, started_at, completed_at?}`; the correct option is never sent
  before the answer. `difficulty_change {from_level, to_level, reason: correct_streak|
  wrong_streak|level_exhausted, streak}`; `level` is the difficulty of the current question (provisional `QUIZ_START_LEVEL=2`, `QUIZ_STREAK=2`, `QUIZ_LENGTH=5`).
  Quizzes never call the model and do not count toward the allowance.
- `LearningRecordEntry {id, submission_id, error_type, topic_id?, topic_name?, topic_deleted,
  created_at}`
