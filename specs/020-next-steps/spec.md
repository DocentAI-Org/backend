# Feature Specification: Next Steps

**Feature Branch**: `020-next-steps`

**Created**: 2026-11-08

**Status**: Draft

**Input**: The learning record, the mastery by topic and the repeated mistakes are computed but only
shown: nothing tells the student what to do next. This feature turns them into a short, ordered
list of recommended next steps per course, each with its basis (§4.7), for requirements S5, S6,
S7 and S8 ("personalised learning").

**Builds on**: [005](../005-repeated-mistakes/spec.md) (repeated mistakes),
[006](../006-adaptive-quizzes/spec.md) (quizzes), [007](../007-progress/spec.md) (mastery),
[008](../008-pre-post-tests/spec.md) (pre/post tests), [015](../015-pedagogy-criteria/spec.md)
(the course's criteria). **Frontend**: `frontend/specs/020-next-steps`.

## Decision (provisional)

Computed on read from data the platform already has; no model call, no new table. The steps are
ranked by a fixed rule (the pedagogy team may change it, like the other provisional criteria):

1. **`test`**: an open pre- or post-test the student has not taken (the study depends on it).
2. **`resume_quiz`**: the latest unfinished quiz.
3. **`review_mistake`**: the student's most repeated mistake pattern (error type and topic) in
   the course's repeated-mistake window, if it reaches the threshold (spec 005); ties go to the
   most recent. It points at the latest submission of the pattern and says whether its review
   was already requested.
4. **`practice_topic`**: the topic with the lowest score among those `starting` or
   `progressing` (spec 007); ties go to course order.
5. **`start_topic`**: the first topic, in course order, `not_started` or `insufficient`.

At most **three** steps, in that order, one of each kind (two for `test` if both phases are open).
`practice_topic` and `start_topic` say whether the topic has approved quiz questions, so the
client can offer a quiz or else the tutor. Graded work without a topic is not recommended.
An empty list means there is nothing to recommend (every topic mastered, or no topics).

The basis travels as data, not text: the client writes the one-sentence reason (§4.7). The teacher
sees exactly the same list for each student (constitution I).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The student sees what to do next (Priority: P1) 🎯

1. **Given** a student with no activity in a course with topics, **When** they read their next
   steps, **Then** they get `start_topic` for the first topic.
2. **Given** an open pre-test the student has not taken, **Then** `test {phase: "pre"}` comes
   first; once submitted, it is gone.
3. **Given** an unfinished quiz, **Then** `resume_quiz` carries its id, answered and total.
4. **Given** 3 mistakes of one type in one topic within the window, **Then** `review_mistake`
   carries the error type, topic, count, window and latest submission; below the threshold, or
   older than the window, there is none.
5. **Given** two topics with scores 0.2 and 0.5 (both under `mastered`), **Then**
   `practice_topic` is the 0.2 one with its level, score and number of items.
6. **Given** every topic mastered, **Then** the list is empty.
7. **Given** more than three candidates, **Then** only the first three by the rule are returned.

### User Story 2 — The teacher sees the same steps (Priority: P2)

1. **Given** a student of their course, **When** the teacher reads that student's next steps,
   **Then** they are identical to the student's; another teacher's course gives 404.

## Requirements *(mandatory)*

- **FR-001**: `GET /v1/student/courses/{id}/next-steps` and
  `GET /v1/teacher/courses/{id}/students/{student_id}/next-steps` return `NextSteps {steps}`,
  `steps` a list discriminated by `kind`.
- **FR-002**: Thresholds come from the course's criteria in effect (spec 015): repeated mistakes
  and mastery.
- **FR-003**: Read-only: reading the steps changes nothing and does not count toward any allowance.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes.
