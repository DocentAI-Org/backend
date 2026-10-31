# Feature Specification: Progress and Mastery by Topic

**Feature Branch**: `007-progress`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "The student sees their progress per course topic over time, with a
mastery level and their most frequent mistakes; the teacher sees the same on the student's page"
(requirements **S7** and **T8**; frontend 001 US13 and US15).

**Builds on**: [003](../003-exercise-feedback/spec.md) (graded exercises, learning record),
[004](../004-teacher-dashboard/spec.md) (weekly activity, provisional criteria),
[006](../006-adaptive-quizzes/spec.md) (quiz answers).

## Clarifications

### Session 2026-10-31

- Q: What is mastery? → A: Provisional: the share right among the student's last
  `PROGRESS_WINDOW` (10) graded items in the topic. An exercise counts 1 if correct, ½ if
  partially correct and 0 if incorrect (not assessed ones do not count); a quiz answer counts 1
  or 0. With fewer than `PROGRESS_MIN_ITEMS` (3) items the level is `insufficient`; without any,
  `not_started`. Otherwise `starting` below 0.5, `progressing` below 0.8, `mastered` from 0.8
  (`PROGRESS_PROGRESSING`, `PROGRESS_MASTERED`). Set in configuration until the educational
  stream agrees a definition.
- Q: "Over time"? → A: The score at the end of each of the last 8 weeks (Monday, UTC, as the
  dashboard), computed with the items up to then; null where there were too few.
- Q: Which activity has a topic? → A: Exercises classified into a course topic and quiz answers
  (their question's topic). Graded activity without a topic is shown apart as "Sin tema".
- Q: Exercise feedback (spec 003) only gave a topic to mistakes, so correct exercises could not
  count toward a topic. → A: The feedback classifies the topic of every graded exercise, correct
  ones included (prompt and validation). Correct exercises from before have no topic and count as
  `unassigned`. The learning record still holds mistakes only.
- Q: What does the teacher see? → A: Exactly what the student sees (same basis, constitution I),
  plus completed quizzes in the weekly activity of the student's page.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The student sees their progress by topic (Priority: P1) 🎯

**Role**: Student · **Covers**: S7

**Acceptance Scenarios**:

1. **Given** graded exercises and quiz answers in a topic, **When** the student reads their
   progress, **Then** the topic carries its level, its score, the basis (exercises right,
   partially right and total; quiz answers right and total), the last activity and the criteria
   applied.
2. **Given** more than `PROGRESS_WINDOW` items, **Then** only the latest ones count.
3. **Given** fewer than `PROGRESS_MIN_ITEMS` items, **Then** the level is `insufficient` and the
   score is null; a topic without items is `not_started`. Every course topic is listed, in course
   order.
4. **Given** activity over several weeks, **Then** `history` has 8 weekly scores, oldest first,
   null where there were too few items by then.
5. **Given** classified mistakes in a topic, **Then** the topic lists its three most frequent
   error types with their count and the latest submission of each.
6. **Given** a correct exercise of a topic, **Then** its feedback carries that topic and it
   counts toward the topic's mastery.
7. **Given** graded exercises without a topic, **Then** they appear in `unassigned`; not
   assessed exercises never count.
8. **Given** no activity, **Then** every topic is `not_started` and `updated_at` is null.

### User Story 2 — The teacher sees the same progress (Priority: P1)

**Role**: Teacher · **Covers**: T8

**Acceptance Scenarios**:

1. **Given** the teacher of the course, **When** they read a student's progress, **Then** it is
   identical to what the student sees.
2. **Given** another teacher, or a student who is not in the course, **Then** 404.
3. **Given** completed quizzes, **Then** the student's weekly activity (spec 004) counts them in
   a new `quizzes` column.

## Requirements *(mandatory)*

- **FR-001**: `GET /v1/student/courses/{course_id}/progress` and
  `GET /v1/teacher/courses/{course_id}/students/{student_id}/progress` → `Progress {provisional,
  criteria {window, min_items, progressing, mastered}, updated_at, quizzes_completed, topics:
  [TopicProgress], unassigned: TopicProgress | null}`.
- **FR-002**: `TopicProgress {topic_id, topic_name, level, score, basis {exercises_correct,
  exercises_partial, exercises_total, quiz_right, quiz_total}, history: [{week_start, score}],
  top_errors: [{error_type, count, latest_submission_id}], last_activity_at}`; the basis counts
  the items in the window, so it explains the score.
- **FR-003**: `WeekActivity` gains `quizzes` (completed that week). Additive.
- **FR-004**: Computed on read from existing data; no new tables; no model calls.
- **FR-005**: Exercise feedback MUST classify the course topic of correct exercises too (spec 003
  change).

## Success Criteria *(mandatory)*

- **SC-001**: Every acceptance scenario has an API test; the suite passes.
- **SC-002**: Unit tests cover the score, the levels and the weekly history.

## Assumptions

- Mistakes from quizzes have no error type, so `top_errors` comes from exercises only.
- Topics deleted later: their exercises keep the topic name (spec 003) but no topic id, so they
  count as `unassigned`.
