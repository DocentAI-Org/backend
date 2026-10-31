# Feature Specification: Study Data Export

**Feature Branch**: `011-study-export`

**Created**: 2026-10-31

**Status**: Draft

**Input**: Requirement **P5** "Export of anonymised data for the study analysis"; the data the
KPIs need are listed in requirements §5. Spec 008 left the export of test results to this
feature.

**Frontend**: the download button is `frontend/specs/012-study-export`.

## Decisions (provisional, for the study team and the Data Protection Officer)

- **Who exports**: the admin (study team). Teachers already see their own courses in the app.
- **Who is in it**: students whose latest consent event is "given". A student who never
  consented or revoked is left out entirely.
- **Identifiers**: each student is a `study_ref`, a keyed hash with its own secret
  (`STUDY_EXPORT_SECRET`): stable across exports, so pre-test and post-test join, but not the
  `student_ref` of the interaction logs, so the export cannot be joined with the database
  without the secret. This is **pseudonymised** data in GDPR terms; anonymisation proper
  (dropping the key, coarsening dates) is for the study team once the data are final.
- **No free text**: no messages, statements, worked answers, explanations, questions or
  corrections, which can contain names or other personal data. Only labels, numbers and dates.
- **No account data**: no names, emails, pseudonym codes, or teacher identities. Courses are
  their ids; topics keep their names (course material, not personal data).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The study team downloads the data (Priority: P1) 🎯

1. **Given** an admin, **When** they request the export, **Then** they get a ZIP with one CSV per
   table below and a `README.md` describing each column.
2. **Given** a `course_id`, **Then** only that course is exported.
3. **Given** a teacher or a student, **Then** the request is rejected (403).

### User Story 2 — Only consenting students, no personal data (Priority: P1)

1. **Given** a student who revoked consent or never gave it, **Then** none of their rows appear.
2. **Given** any export, **Then** no file contains a student's account id, name, email, pseudonym
   code, `student_ref`, or any free text the student, the teacher or the model wrote.
3. **Given** two exports, **Then** the same student has the same `study_ref` in both.

## Files

| File | One row per | Columns |
|---|---|---|
| `students.csv` | consenting student and course | study_ref, course_id, joined_at, consent_version |
| `topics.csv` | course topic | course_id, topic_id, topic_name |
| `messages.csv` | chat message | study_ref, course_id, conversation_id, author, kind, hint_number, request_solution, created_at |
| `exercises.csv` | exercise submission | study_ref, course_id, submission_id, verdict, error_type, topic_id, topic_name, created_at |
| `quiz_items.csv` | quiz question shown | study_ref, course_id, quiz_id, position, topic_id, topic_name, difficulty, correct, answered_at |
| `tests.csv` | pre/post-test answer | study_ref, course_id, phase, question_id, topic_id, topic_name, correct, submitted_at |
| `interactions.csv` | model call (P2) | study_ref, course_id, kind, model, input_tokens, output_tokens, latency_ms, estimated_cost_usd, outcome, created_at |

## Requirements *(mandatory)*

- **FR-001**: `GET /v1/admin/study-export` (optional `course_id`) returns `application/zip`.
- **FR-002**: `STUDY_EXPORT_SECRET` MUST be set apart from `LOG_PSEUDONYM_SECRET`.
- **FR-003**: No database change.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario, including a check that no personal value or free
  text of the fixtures appears anywhere in the ZIP; the full suite passes.
