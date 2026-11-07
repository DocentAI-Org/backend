# Feature Specification: Student Erasure on Request

**Feature Branch**: `017-student-erasure`

**Created**: 2026-11-07

**Status**: Draft

**Input**: Requirements §4.1 "Erasure on request removes a student and everything linked to them"
and constitution VI. The pilot (February 2027) cannot start without it.

**Frontend**: the admin's delete action is a later frontend spec.

## Decisions (provisional, for the study team and the Data Protection Officer)

- **Who erases**: the admin (study team), on the student's request. Students do not erase
  themselves in the app: the request goes through the study team, who check who is asking.
- **Who can be erased**: only student accounts. Erasing a teacher would delete their courses and
  every student's work in them, so a teacher or admin is refused (409).
- **What goes**: the auth account, and with it the profile and every row that references it
  (enrolments, consent events, conversations and messages, exercise submissions, learning record,
  mistake reviews, quizzes, test answers, daily usage, favourites, tags, and teacher flags and
  corrections on the student's messages). The database already cascades all of these from
  `auth.users`. The interaction logs (P2) store `student_ref`, a keyed hash, not the account id,
  so they are deleted by that hash in the same request.
- **What stays**: course material, topics, quiz questions and test questions (written by
  teachers, not about the student), and earlier study exports already downloaded (P5): they hold
  `study_ref` and no personal data; the study team deletes the student's rows there by hand if
  the request asks for it.
- **No trace kept**: the response tells the admin what was deleted; nothing about the erased
  student is stored afterwards. The study team records the request in their own register.
- **Retention** (deleting everything when the study ends) is a separate spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The admin erases a student (Priority: P1) 🎯

1. **Given** an admin and a student with data in every table above, **When** the admin erases
   the student, **Then** the response is 200 with the number of rows deleted per kind, and none
   of the student's rows remain, including their interaction logs.
2. **Given** another student in the same course, **Then** none of their rows are touched.
3. **Given** an erased student, **When** they call the API with a token issued before the
   erasure, **Then** the request is rejected (401).
4. **Given** an erased student, **When** the admin erases them again, **Then** 404.

### User Story 2 — Only students, only by the admin (Priority: P1)

1. **Given** a teacher or an admin account, **When** the admin tries to erase it, **Then** 409
   `not_a_student` and nothing is deleted.
2. **Given** a teacher or a student, **When** they call the endpoint, **Then** 403.
3. **Given** the auth service fails, **Then** 503 and nothing is deleted.

## Requirements *(mandatory)*

- **FR-001**: `DELETE /v1/admin/students/{student_id}` returns `StudentErasure` with
  `student_id` and counts of deleted rows: `courses` (enrolments), `conversations`, `messages`,
  `exercise_submissions`, `quizzes`, `test_attempts`, `interaction_logs`.
- **FR-002**: The auth account is deleted through the Supabase Auth admin API, after the
  interaction logs are deleted in the request's transaction, so an auth failure rolls them back.
- **FR-003**: No database change.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario, with a check over every table that references
  `profiles` that no row of the erased student remains; the full suite passes.
