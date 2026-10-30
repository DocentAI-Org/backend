# Feature Specification: Teacher Dashboard — Recurring Errors and At-Risk Students

**Feature Branch**: `004-teacher-dashboard`

**Created**: 2026-10-30

**Status**: Draft

**Input**: User description: "Teacher dashboard with recurring errors by topic and by student, and
at-risk students with provisional criteria (OQ12 is not agreed yet)."

**Builds on**: [003](../003-exercise-feedback/spec.md) (learning record with error type and topic)
and requirement **T5** (`knowledge-base/docs/requirements.md`); the at-risk part of **T8**.
Criteria: [risk-criteria.md](risk-criteria.md).

## Clarifications

### Session 2026-10-30

- Q: The at-risk criteria (OQ12) are not agreed. What do we use? → A: Provisional, explainable
  criteria stored as data, like the taxonomy, each flag stating its basis in one sentence.
- Q: Fixed or set by the teacher? → A: Fixed and provisional for now; in the future teachers
  should configure them per course wherever possible. The design must allow per-course overrides
  without changing the API shape (see Assumptions).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The teacher sees recurring errors by topic and by student (Priority: P1) 🎯

**Role**: Teacher · **Covers**: T5

**Acceptance Scenarios**:

1. **Given** a course with learning-record entries, **When** the teacher reads the dashboard for a
   period (7 days, 30 days or the whole course), **Then** they get the errors grouped by topic
   (count, number of students, most frequent type) and grouped by student (count, most frequent
   type and topic), both sorted by count, only with entries in the period.
2. **Given** entries without a topic, **Then** they are grouped under "no topic"; entries of a
   deleted topic keep its name and are marked as deleted.
3. **Given** a course with less activity in the period than 20 messages to the tutor or 5
   exercises, **Then** the dashboard says there is not enough data and returns the activity counts
   and the thresholds, so the app can say what is missing.
4. **Given** a revoked student, **Then** their entries are not counted and they are not listed.
5. **Given** a teacher who does not own the course, **Then** `404`.

### User Story 2 — The teacher sees at-risk students and why (Priority: P1)

**Role**: Teacher · **Covers**: T5, T8

**Acceptance Scenarios**:

1. **Given** a student with no activity in the last 7 days, **When** the teacher reads the
   dashboard, **Then** the student is listed as at risk with reason `inactive`, the number of days
   and the date of the last activity (or of joining, if there was none).
2. **Given** a student with at least 5 assessed exercises in the last 14 days and 60 % or more
   with a mistake, **Then** they are listed with reason `error_rate` and the counts (e.g. 6 of 10).
3. **Given** a student who meets both criteria, **Then** they are listed once with both reasons.
4. **Given** a student who meets none, or whose only exercises are `not_assessed`, **Then** they
   are not listed.
5. **Given** a course student, **When** the teacher reads that student's risk status, **Then**
   they get the same reasons (an empty list if not at risk), the last activity and the activity per
   week for the last 8 weeks.

### User Story 3 — Anyone in the course can read the criteria (Priority: P2)

1. **Given** a teacher, **When** they list the criteria, **Then** they get each code, its
   thresholds, whether it is enabled, and whether the criteria are provisional.

### Edge Cases

- The at-risk list does not depend on the selected period: each criterion has its own window.
- A student who joined less than 7 days ago with no activity is not `inactive` yet.
- A disabled criterion is never applied.
- Entries with a type that is not in the taxonomy (the v1 `placeholder`) are not counted.

## Requirements *(mandatory)*

- **FR-001**: `GET /v1/teacher/courses/{course_id}/dashboard?period=7d|30d|all` (default `30d`)
  MUST return `errors_by_topic`, `errors_by_student`, `at_risk`, `activity` (student messages and
  exercises in the period), `enough_data` with its thresholds, and `criteria_provisional`.
- **FR-002**: `GET /v1/teacher/courses/{course_id}/students/{student_id}/risk` MUST return
  `reasons`, `last_activity_at` and `weekly_activity` (8 weeks, Monday-based).
- **FR-003**: `GET /v1/teacher/risk-criteria` MUST list the criteria.
- **FR-004**: Every reason MUST carry the values behind it (days and date, or mistakes and assessed
  exercises with the window), so the app can show the basis in one sentence (requirements:
  transparency rule; Constitution I).
- **FR-005**: The criteria MUST be data (`risk_criteria`: code, position, enabled, thresholds as
  JSON, provisional), seeded with [risk-criteria.md](risk-criteria.md); nothing about risk is
  stored per student.
- **FR-006**: Students MUST be shown by display name or pseudonym only (FR-043), and no data MUST
  leave the course: no model is involved.
- **FR-007**: The dashboard MUST be computed in a bounded number of queries (no query per student).

## Success Criteria *(mandatory)*

- **SC-001**: Every acceptance scenario has an API test; the full suite passes.
- **SC-002**: On a seeded course with 30 students and 1,000 entries, the dashboard answers in
  under 300 ms locally.

## Assumptions

- Quizzes (S6, T6) do not exist yet; when they do, quiz mistakes join the error counts.
- Mastery (OQ9) is out of scope.
- Teacher-set criteria are a later feature: a per-course table (e.g. `course_risk_criteria`)
  overriding `enabled` and thresholds of the global defaults. To keep that change small, the
  service MUST resolve the criteria for a course in one function (`criteria_for(course)`), and the
  responses MUST carry the thresholds actually applied, never assume the global ones.
