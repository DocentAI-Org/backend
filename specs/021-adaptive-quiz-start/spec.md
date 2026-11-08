# Feature Specification: Quizzes That Start From the Student's Mastery

**Feature Branch**: `021-adaptive-quiz-start`

**Created**: 2026-11-08

**Status**: Draft

**Input**: Requirement **S6** ("adaptive quizzes, difficulty follows performance") and §4.7. Today
every quiz starts at `QUIZ_START_LEVEL=2` for everyone and only adapts within the quiz; the
mastery already computed per topic (spec 007) is ignored, and a quiz on every topic draws
questions without regard for the student's weak topics. The quiz settings are also the last
pedagogical values still in `.env`, outside the course criteria (spec 015).

**Builds on**: [006](../006-adaptive-quizzes/spec.md) (quizzes), [007](../007-progress/spec.md)
(mastery), [015](../015-pedagogy-criteria/spec.md) (criteria per course).
**Frontend**: `frontend/specs/021-adaptive-quiz-start`.

## Decision (provisional)

- A new criteria group, **`quiz {length, streak, start_level, adaptive}`**, replaces `QUIZ_LENGTH`,
  `QUIZ_STREAK` and `QUIZ_START_LEVEL` with the same values (5, 2, 2) and `adaptive: true`. Like
  every group, the admin sets the study's and a teacher may override it for a course.
- With `adaptive`, a quiz **starts at the level of the student's mastery**: `starting` → 1,
  `progressing` → 2, `mastered` → 3. For a topic quiz, the topic's mastery; for a quiz on every
  topic, the mean score of the topics that have one, read with the same thresholds. Without a
  score (`not_started`, `insufficient`) or without `adaptive`, it starts at `start_level`.
- With `adaptive`, a quiz on every topic **favours weak topics**: among the questions nearest to
  the target level and answered least, the topic with the lowest score comes first. A topic
  without a score counts as `progressing` (the threshold), so new topics are neither pushed nor
  hidden.
- The **basis of the start is stored with the quiz** (`start_basis`) so it never changes, and
  shown to the student and the teacher: `{reason: mastery|no_score|fixed, mastery_level?,
  score?}`.
- As before, the level is the difficulty of the question shown: if no question exists at the
  target level, the nearest one is used.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The quiz starts where the student is (Priority: P1) 🎯

1. **Given** a topic the student masters (score ≥ 0.8), **When** they start a quiz on it,
   **Then** the first question is at level 3 and `start_basis` is `{reason: "mastery",
   mastery_level: "mastered", score}`.
2. **Given** a topic at `starting`, **Then** the first question is at level 1.
3. **Given** a topic with too few items, **Then** the quiz starts at `start_level` with
   `{reason: "no_score"}`.
4. **Given** `adaptive: false` for the course, **Then** it starts at `start_level` with
   `{reason: "fixed"}` whatever the mastery.
5. **Given** a quiz on every topic, **Then** the start uses the mean score of the scored topics.

### User Story 2 — A quiz on every topic favours weak topics (Priority: P1)

1. **Given** two topics with questions at the same level, one at 0.2 and one at 0.9, **When** the
   student starts a quiz on every topic, **Then** the first question is from the weak topic.
2. **Given** `adaptive: false`, **Then** the order is the previous one (level, least answered,
   difficulty, creation).

### User Story 3 — The settings are course criteria (Priority: P2)

1. **Given** the study defaults, **Then** `quiz` is `{length: 5, streak: 2, start_level: 2,
   adaptive: true}`.
2. **Given** a course with `quiz.length = 3` and `quiz.streak = 1`, **Then** its quizzes have 3
   questions and one right answer moves the level up.
3. **Given** invalid values (length 0 or > 30, streak 0 or > 10, level outside 1–3), **Then** 422.

## Requirements *(mandatory)*

- **FR-001**: Migration: `pedagogy_criteria.quiz` (seeded on the defaults row; required there) and
  `quizzes.start_basis` (nullable JSON; null for quizzes started before).
- **FR-002**: `Quiz.start_basis` in the student's and the teacher's views.
- **FR-003**: `QUIZ_*` settings are removed from the configuration and `.env.example`.
- **FR-004**: Answering still never calls the model.

## Success Criteria *(mandatory)*

- **SC-001**: API tests cover every scenario; the full suite passes.
