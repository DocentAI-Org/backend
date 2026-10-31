# Feature Specification: Quiz Questions Approved by the Teacher and Adaptive Quizzes

**Feature Branch**: `006-adaptive-quizzes`

**Created**: 2026-10-31

**Status**: Draft

**Input**: User description: "The teacher reviews and approves AI-generated quiz questions; the
student takes short quizzes whose difficulty follows their performance, with immediate
feedback" (requirements **T7** and **S6**; frontend 001 US10 and US11).

**Builds on**: [001](../001-api-v1-contract/spec.md) (topics, assignments, tutor settings),
[005](../005-repeated-mistakes/spec.md) (provisional, configurable rules).

## Clarifications

### Session 2026-10-31

- Q: What kind of question? → A: Multiple choice with four options and one correct answer, so
  answers are graded without the model and feedback is immediate. Other kinds can come later.
- Q: How is difficulty expressed? → A: Three levels, `1` basic, `2` intermediate, `3` advanced,
  proposed by the model and editable by the teacher.
- Q: How does the difficulty adapt? → A: Provisional: a quiz starts at level 2; after
  `QUIZ_STREAK` (2) correct answers in a row the level goes up one, after the same number of
  wrong answers in a row it goes down one, and the streak restarts. Each change carries its
  reason so the interface can say it in plain language (frontend FR-016). Set in configuration
  (`QUIZ_LENGTH` = 5, `QUIZ_STREAK` = 2, `QUIZ_START_LEVEL` = 2) until the educational stream
  agrees a rule.
- Q: Which material do generated questions come from? → A: The material assigned to the topic
  (confirmed assignments: whole documents or sections); if the topic has none, the validated
  material most similar to the topic name. Every question cites the fragment it comes from.
- Q: Do quizzes count toward the student's daily allowance? → A: No. Answering a quiz never calls
  the model. Generating questions is a teacher action, logged with its cost but not charged to
  any student.

### Session 2026-10-31 (after the real-stack walkthrough, frontend 008)

- Q: The local model labelled every draft "Fácil", so a quiz "at level 2" showed easy questions
  and could say it lowered the level while they were already easy. What is the level? → A: The
  difficulty of the question being shown. A quiz starts at the available level nearest to
  `QUIZ_START_LEVEL`; a streak moves the target one level, and the level changes only when the
  next question really is at another level. With no question left at the level, the quiz moves
  to the nearest one with reason `level_exhausted`. No change is reported after the last answer.
- Q: How do we get questions at every level? → A: The request tells the model how many to write
  at each level, spread evenly (5 → two at 1, two at 2, one at 3).
- Q: Can students choose a topic before their first quiz? → A: Yes: a student route lists the
  course topics that have approved questions, with how many.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The teacher asks the AI for draft questions (Priority: P1) 🎯

**Role**: Teacher · **Covers**: T7

**Acceptance Scenarios**:

1. **Given** a topic with material, **When** the teacher asks for N questions (1–10, default 5),
   **Then** up to N questions are stored as `pending`, each with a statement, four options, the
   correct option, a short explanation, a difficulty and at least one citation; the response
   lists them.
2. **Given** a model reply where some drafts are unusable (not four distinct options, no valid
   correct option, no valid citation, empty text), **Then** those drafts are dropped and the
   others kept; if none is usable, the response is an empty list with `kind: no_source`.
3. **Given** a topic with no retrievable material, **Then** nothing is generated and the
   response has `kind: no_source`, without calling the model.
4. **Given** the provider fails, **Then** `503 tutor_unavailable` and nothing is stored.
5. **Given** any generation request, **Then** it is logged as an interaction of kind
   `quiz_generation` with tokens, cost and latency, and no student reference.
6. **Given** a course of another teacher, **Then** 404.

### User Story 2 — The teacher reviews, edits, approves and rejects questions (Priority: P1)

**Role**: Teacher · **Covers**: T7

**Acceptance Scenarios**:

1. **Given** questions, **When** the teacher lists them (filter by status and topic), **Then**
   each shows its text, options, correct option, explanation, difficulty, topic, citations and
   status, and the response carries the count per status.
2. **Given** a question, **When** the teacher edits it (text, options, correct option,
   explanation, difficulty), **Then** it is saved; an edited AI draft is marked `edited`.
3. **Given** a question, **When** the teacher approves or rejects it (optionally with edits in
   the same request), **Then** its status changes and the counts update.
4. **Given** invalid edits (not four options, duplicated options, correct option out of range,
   difficulty outside 1–3), **Then** `422`.
5. **Given** an approved question that students have answered, **Then** it shows how many
   times it was answered and the share answered correctly.

### User Story 3 — The student takes an adaptive quiz (Priority: P1)

**Role**: Student · **Covers**: S6

**Acceptance Scenarios**:

1. **Given** approved questions in the course, **When** the student starts a quiz (optionally
   for one topic), **Then** they get the quiz with its topic, the number of questions
   (`QUIZ_LENGTH` or fewer if there are fewer approved questions) and the first question at
   the start level, without the correct option.
2. **Given** no approved question (for that topic), **Then** `409 no_questions`.
3. **Given** the current question, **When** the student answers, **Then** they get at once
   whether it was right, the correct option, the explanation and the citations, and the next
   question; answering a question that is not the current one is `409 not_current_question`.
4. **Given** `QUIZ_STREAK` correct (or wrong) answers in a row, **Then** the answer carries
   `difficulty_change {from, to, reason, streak}` and the next question is one level up (down),
   within 1–3, if the course has one. With no question left at a level, the nearest level is
   used and the change says `level_exhausted`. Without questions at another level, nothing
   changes and no change is reported.
5. **Given** the last answer, **Then** the quiz is `completed` and carries a summary: score,
   score by topic, and the final level.
6. **Given** a question the student has seen in an earlier quiz, **Then** unseen questions are
   preferred.
7. **Given** a question the teacher edits or rejects after the quiz started, **Then** the quiz
   keeps the version the student saw.
8. **Given** approved questions in some topics, **When** the student lists the quiz topics,
   **Then** they get those topics with their number of approved questions, in course order.
9. **Given** a student without study consent, **Then** `409 consent_required`, as for the tutor.
   Another student's quiz is 404.

## Requirements *(mandatory)*

- **FR-001**: `quiz_questions` per course and topic: `statement`, `options` (4), `correct_option`
  (0–3), `explanation`, `difficulty` (1–3), `status: pending|approved|rejected`, `origin:
  ai|edited`, citations; the teacher's id and time of the last review.
- **FR-002**: Teacher routes under `/v1/teacher/courses/{course_id}`:
  `POST /topics/{topic_id}/questions/generate {count}`, `GET /questions?status&topic_id`
  (with `counts`), `PATCH /questions/{question_id}` (edits and/or `status`).
- **FR-003**: Generation MUST be grounded only in validated material retrieved for the topic,
  with the same prompt-injection rules as the tutor and citations only to fragments given; no
  personal data is sent to the model. The tutor level and tone apply.
- **FR-004**: Student routes under `/v1/student/courses/{course_id}`: `POST /quizzes {topic_id?}`,
  `GET /quizzes`, `GET /quizzes/{quiz_id}`, `POST /quizzes/{quiz_id}/answers {question_id,
  choice}`. Students only ever see approved questions, and never the correct option before
  answering.
- **FR-005**: Each quiz item stores a snapshot of the question as shown (statement, options,
  correct option, explanation, difficulty, topic) and the answer, so later edits do not change
  past quizzes or the study data.
- **FR-006**: The adaptive rule (start level, streak, length) is provisional configuration. The
  quiz level is the difficulty of the current question.
- **FR-007**: `GET /v1/student/courses/{course_id}/quiz-topics` →
  `[{topic_id, topic_name, question_count}]`, approved questions only.

## Success Criteria *(mandatory)*

- **SC-001**: Every acceptance scenario has an API test with the fake model; the suite passes.
- **SC-002**: Against the local Ollama model, generating 5 questions for "Quitar paréntesis" on
  the `ecuaciones.md` fixture gives at least 3 usable questions citing § 3.3, recorded with their
  defects in `validation.md`.

## Assumptions

- Quiz mistakes do not go to the learning record yet: questions have no error type. Repeated
  mistake patterns (005) and the dashboard (004) keep counting exercises only.
- A student may leave a quiz unfinished; it stays `in_progress` and does not block a new one.
- The student's progress view (S7) and the teacher's per-student view (T8) will read quiz
  results later.
