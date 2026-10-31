# Feature Specification: Configurable Pedagogical Criteria

**Feature Branch**: `015-pedagogy-criteria`

**Created**: 2026-11-01

**Status**: Draft

**Input**: User description: "Implement something easily configurable" for the open questions
that keep criteria provisional: OQ12 (who defines the at-risk criteria), OQ9 (what mastering a
topic means), OQ3 (what is adapted). The study team sets the defaults; each teacher may adjust
them in their course (decided 2026-11-01).

**Frontend**: `frontend/specs/015-pedagogy-criteria`.

## Today

| Criteria | Where | Used by |
|---|---|---|
| At-risk: inactive, error rate (spec 004) | `risk_criteria` table, global | teacher dashboard |
| Repeated mistakes (spec 005) | `REPEATED_MISTAKE_COUNT/DAYS` env | feedback notice, review |
| Adaptation (spec 013) | always on, spec 005 thresholds | tutor, feedback |
| Mastery (spec 007) | `PROGRESS_*` env | progress (student and teacher) |

Env values need a redeploy; nothing is per course.

## Decisions

- One table, `pedagogy_criteria`: one row for the **study defaults** (`course_id` null) and at
  most one per course with the teacher's **overrides**. Five groups, each overridden whole or
  not at all: `inactive`, `error_rate`, `repeated_mistakes`, `adaptation`, `mastery`.
- The defaults start with today's values (the `risk_criteria` rows and the env defaults), so
  nothing changes until someone edits them; `risk_criteria` and the env settings are removed.
- `provisional` belongs to the study defaults: true until the educational stream agrees them;
  dashboard and progress keep showing it.
- The adaptation's repeated-mistake threshold is the course's `repeated_mistakes` group.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The study team sets the defaults (Priority: P1) 🎯

1. **Given** an admin, **When** they read the study criteria, **Then** they get every group's
   values, `provisional` and when they were last changed.
2. **When** they save new values (or mark them as no longer provisional), **Then** every course
   without its own values for a group uses them at once.
3. **Given** invalid values (a rate outside 0–1, "progressing" not below "mastered", fewer items
   in the window than needed for a level, days or counts below 1), **Then** 422 and nothing
   changes.
4. **Given** a teacher or a student, **Then** 403.

### User Story 2 — A teacher adjusts their course (Priority: P1)

1. **Given** the teacher of a course, **When** they read its criteria, **Then** they get the
   study values, which groups the course overrides, and the values in effect.
2. **When** they save their own values for a group, **Then** only that course uses them; a
   group sent as `null` goes back to the study values.
3. **Given** another teacher's course, **Then** 404.

### User Story 3 — Every feature uses the course's criteria (Priority: P1)

1. **Given** a course with `inactive.days = 3`, **Then** a student inactive for 4 days is at
   risk on that course's dashboard, and not on another course with the default 7.
2. **Given** `repeated_mistakes.count = 2`, **Then** the second same mistake shows the notice.
3. **Given** `adaptation.enabled = false`, **Then** no answer is adapted in that course.
4. **Given** `mastery.mastered = 0.6`, **Then** the progress levels and the criteria shown
   follow it.

## Requirements *(mandatory)*

- **FR-001**: `GET/PUT /v1/admin/pedagogy-criteria`; `GET/PUT
  /v1/teacher/courses/{course_id}/pedagogy-criteria`.
- **FR-002**: Migration: table (RLS on, no client access), default row from today's values,
  `risk_criteria` dropped. API responses that report criteria keep their shape.
- **FR-003**: All consumers read the effective criteria of the course through one function.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes.
