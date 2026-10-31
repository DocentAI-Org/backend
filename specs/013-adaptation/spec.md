# Feature Specification: Explanations Adapted to the Student

**Feature Branch**: `013-adaptation`

**Created**: 2026-10-31

**Status**: Draft

**Input**: Requirement **S8** "The tutor adapts its explanations to the individual student, using
their learning record (recurring error types, topic progress) and within the teacher's T3
settings. An adapted explanation says that it was adapted and why, in one sentence." and §4.7
(the same basis shown to the student and to their teacher).

**Builds on**: [005](../005-repeated-mistakes/spec.md) (repeated mistakes and their thresholds).
**Frontend**: `frontend/specs/014-adaptation`.

## Decision (provisional, open question OQ3 of the requirements)

What is adapted is not agreed yet (OQ3: prior errors, level, examples, pace). This feature takes
the one dimension the data already supports and the requirement names first: **recurring error
types**.

- A student's *focus* in a course is the error type they made most often in the last
  `REPEATED_MISTAKE_DAYS` days (default 30), if at least `REPEATED_MISTAKE_COUNT` times
  (default 3), the thresholds of spec 005. Ties go to the most recent.
- With a focus, the tutor's chat answers and exercise feedback are asked to pay special attention
  to that kind of mistake; the teacher's level, tone and solution policy still apply.
- The reason shown is built from the data, not written by the model: error type, count and days.
  It is stored with the answer, so it does not change later.
- The model gets only the error type's name and description and the count: nothing that
  identifies the student.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The tutor takes recurring mistakes into account (Priority: P1) 🎯

1. **Given** a student with 3 procedural mistakes in the course in the last 30 days, **When**
   they ask the tutor and get an answer or a hint, **Then** the model was told about that error
   type, and the answer carries `adaptation {error_type, count, window_days}`.
2. **Given** the same student, **When** they submit an exercise that is assessed, **Then** the
   feedback is adapted the same way.
3. **Given** fewer mistakes than the threshold, mistakes older than the window, or mistakes in
   another course, **Then** nothing is adapted and `adaptation` is null.
4. **Given** an answer the material does not cover (`no_source`) or a `not_assessed` exercise,
   **Then** `adaptation` is null.

### User Story 2 — The teacher sees the same basis (Priority: P1)

1. **Given** an adapted answer or feedback, **When** the teacher reads the conversation or the
   submission, **Then** they see the same `adaptation`.

## Requirements *(mandatory)*

- **FR-001**: `adaptation` (nullable JSON) on `messages` and `exercise_submissions`; `Adaptation`
  in `StudentMessage` and `StudentSubmission` (and so in the teacher's views).
- **FR-002**: The prompt note is a label (`adaptation` in `policies.md`), not free text.
- **FR-003**: No personal data in the note (constitution; requirements §4.1).

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes.
