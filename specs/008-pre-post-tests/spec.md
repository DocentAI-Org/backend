# Feature Specification: Pre-test and Post-test

**Feature Branch**: `008-pre-post-tests`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "Built-in pre-test and post-test for the pilot, scored per student
and topic" (requirement **P3**; KPI "pre/post-test improvement, topic mastery").

**Builds on**: [006](../006-adaptive-quizzes/spec.md) (multiple-choice questions, topics),
[002](../002-consent-and-flags/spec.md) (study consent).

## Clarifications

### Session 2026-10-31

- Q: Built in or imported? → A: Built in (product owner). Results by student and topic.
- Q: One test or two? → A: One test per course, taken twice: the pre-test before the pilot and the
  post-test after it, with the same questions, so the scores compare.
- Q: Who writes it? → A: The teacher (or the study team on the teacher's account): multiple choice,
  four options, one right, each question in a course topic. Questions can be written or copied
  from the approved quiz questions (spec 006); a copy is independent of its source.
- Q: When can it be taken? → A: Each phase is opened and closed by hand. Once the pre-test has been
  opened, the questions are frozen (`409 test_locked`), so both phases measure the same thing.
- Q: What does the student see? → A: All questions on one page, answered once per phase. No
  correction, score or hints afterwards (it would teach the post-test); only a confirmation.
  Taking it needs study consent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The teacher prepares the test (Priority: P1) 🎯

**Role**: Teacher · **Covers**: P3

**Acceptance Scenarios**:

1. **Given** a course, **When** the teacher adds questions (statement, four options, right option,
   topic), **Then** they are listed in order with their topic; edits and deletions work.
2. **Given** an approved quiz question, **When** the teacher copies it into the test, **Then** a
   new test question with the same content and topic is added.
3. **Given** invalid input (not four distinct options, right option out of range, unknown topic),
   **Then** `422`.
4. **Given** the pre-test has ever been opened, **Then** adding, editing or deleting questions is
   `409 test_locked`.
5. **Given** another teacher's course, **Then** 404.

### User Story 2 — The teacher opens and closes each phase (Priority: P1)

**Acceptance Scenarios**:

1. **Given** questions, **When** the teacher opens the pre-test, **Then** its status is `open`,
   with the time; closing it sets `closed`. The same for the post-test.
2. **Given** no questions, **Then** opening is `409 test_empty`.
3. **Given** a closed phase, **When** the teacher opens it again, **Then** it reopens (late
   students); answers already given stay.

### User Story 3 — The student takes each phase once (Priority: P1)

**Role**: Student · **Covers**: P3

**Acceptance Scenarios**:

1. **Given** an open phase, **When** the student lists the course tests, **Then** they see each
   phase with its status and whether they have done it.
2. **Given** an open phase not done, **When** they open it, **Then** they get every question
   without the right option.
3. **Given** answers to every question, **When** they submit, **Then** `201` with the submission
   time and nothing about right or wrong; missing or unknown questions are `422`.
4. **Given** a phase already done, **Then** submitting again is `409 test_already_done` and
   opening it says it is done.
5. **Given** a phase that is not open, **Then** `409 test_not_open`.
6. **Given** no study consent, **Then** `409 consent_required`.

### User Story 4 — The teacher reads the results (Priority: P1)

**Acceptance Scenarios**:

1. **Given** submissions, **When** the teacher reads the results, **Then** each active student
   shows, for each phase, the score (right / total) and the score by topic, or null if not done;
   and the course average per phase and topic.
2. **Given** a student who did both phases, **Then** the result shows the change per topic.

## Requirements *(mandatory)*

- **FR-001**: Tables `test_questions` (course, topic, position, statement, options, right option),
  `test_phases` (course, phase `pre|post`, status `not_open|open|closed`, opened_at, closed_at,
  first_opened_at) and `test_attempts` / `test_answers` (one attempt per student and phase, its
  answers and whether each was right). Deleting a student deletes their attempts.
- **FR-002**: Teacher routes under `/v1/teacher/courses/{course_id}/test`: `GET` (questions and
  phases), `POST /questions`, `POST /questions/from-quiz {question_id}`, `PATCH|DELETE
  /questions/{id}`, `PUT /phases/{phase} {status}`, `GET /results`.
- **FR-003**: Student routes under `/v1/student/courses/{course_id}/test`: `GET` (phases with
  status and done), `GET /{phase}` (questions without the right option, or `done`),
  `POST /{phase} {answers: [{question_id, choice}]}`.
- **FR-004**: Answers are graded against the question as it was when answered (questions are
  frozen while any phase has been opened).

## Success Criteria *(mandatory)*

- **SC-001**: Every acceptance scenario has an API test; the suite passes.

## Assumptions

- The pilot uses the same questions for both phases; parallel forms are out of scope.
- The export of results for analysis is P5 (next feature).
