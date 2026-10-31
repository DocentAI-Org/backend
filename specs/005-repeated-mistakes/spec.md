# Feature Specification: Targeted Help for Repeated Mistakes

**Feature Branch**: `005-repeated-mistakes`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "When a student repeats the same type of mistake, name the pattern
and offer a targeted explanation and practice" (requirement **S5**; frontend 001 US12).

**Builds on**: [003](../003-exercise-feedback/spec.md) (learning record with error type and topic)
and [004](../004-teacher-dashboard/spec.md) (provisional, explainable criteria).

## Clarifications

### Session 2026-10-31

- Q: What counts as a repeated mistake? → A: Provisional: the same error type in the same topic
  (or both without a topic) at least 3 times in the last 30 days, counting the current one. Set
  in configuration (`REPEATED_MISTAKE_COUNT`, `REPEATED_MISTAKE_DAYS`) until the educational stream
  agrees a definition; teachers may configure it per course later, like the at-risk criteria.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The feedback names the repeated pattern (Priority: P1) 🎯

**Role**: Student, Teacher · **Covers**: S5

**Acceptance Scenarios**:

1. **Given** a student whose new mistake is the 3rd of the same type and topic in 30 days,
   **When** they read the feedback, **Then** it carries `repeated_mistake` with the count, the
   window, the error type and the topic.
2. **Given** the 2nd such mistake, or mistakes of the same type in different topics, **Then**
   `repeated_mistake` is null.
3. **Given** an older submission, **When** it is read again, **Then** the count is the one up to
   that submission (later mistakes do not change it).
4. **Given** a correct, not assessed or unclassified submission, **Then** `repeated_mistake` is
   null.
5. **Given** the teacher reads the same submission, **Then** they see the same
   `repeated_mistake` (transparency rule: same basis to the teacher).

### User Story 2 — The student gets a targeted review (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a submission with a repeated mistake, **When** the student asks for its review,
   **Then** they get what is going wrong, one worked example and two practice statements, all
   grounded in the course material with at least one citation; the request counts toward the
   daily allowance.
2. **Given** a review already exists, **When** the student asks again, **Then** they get the same
   review, the model is not called and nothing is charged.
3. **Given** the material has nothing for that pattern, or the model reply is unusable, **Then**
   the review is stored with kind `no_source` and the "not covered" notice, without practice.
4. **Given** a course whose tutor gives hints only, **Then** the review does not solve the
   student's exercise nor give the answers to the practice statements.
5. **Given** a submission without a repeated mistake, **Then** `409 no_repeated_mistake`.
6. **Given** the model provider fails, **Then** `503 tutor_unavailable`, nothing stored, the
   allowance released.
7. **Given** the daily limit is reached, **Then** `429 daily_limit_reached` (as for exercises).
8. **Given** the teacher of the course, **When** they read the review, **Then** they get the same
   content; another teacher gets 404.

## Requirements *(mandatory)*

- **FR-001**: `StudentSubmission` (and so `TeacherSubmission`) MUST gain
  `repeated_mistake: {count, window_days, error_type, topic_name} | null` (additive).
- **FR-002**: `POST /v1/student/courses/{course_id}/submissions/{submission_id}/review` MUST
  return the review (201 when created, 200 when it already existed);
  `GET` on the same path returns it or 404.
  `GET /v1/teacher/courses/{course_id}/submissions/{submission_id}/review` for the teacher.
- **FR-003**: `MistakeReview {id, submission_id, error_type, topic_name, kind: answer|no_source,
  explanation, worked_example?, practice: [str], citations, created_at}`, stored in
  `mistake_reviews` (one per submission).
- **FR-004**: The review MUST be grounded only in validated material retrieved for the error
  type, the topic and the exercise; same prompt-injection rules and tutor settings as feedback;
  citations only to fragments given; no personal data sent to the model.
- **FR-005**: Every review request that calls the model, or finds no material, MUST be logged
  as an interaction of kind `review`.

## Success Criteria *(mandatory)*

- **SC-001**: Every acceptance scenario has an API test with the fake model; the suite passes.
- **SC-002**: Against the local Ollama model, a third "bracket not distributed" mistake on the
  `ecuaciones.md` fixture gets a review citing § 3.3 "Quitar paréntesis" or nearby material,
  with two practice statements.

## Assumptions

- Quiz mistakes (S6) will count toward patterns when quizzes exist.
- The review is per submission, so a later repetition of the same pattern can get a new one.
