# Tasks: Quiz Questions Approved by the Teacher and Adaptive Quizzes

**Spec**: [spec.md](spec.md)

## Phase 1: Tests first

- [x] T001 [P] API tests: US1 AS1–AS6 and US2 AS1–AS5 in `tests/api/test_quiz_questions.py`
  (fake model)
- [x] T002 [P] API tests: US3 AS1–AS8 in `tests/api/test_quizzes.py`
- [x] T003 [P] Unit tests: draft validation and the adaptive rule in `tests/unit/test_quizzes.py`

## Phase 2: Data

- [x] T004 Migration: `quiz_questions` (+ citations link), `quizzes`, `quiz_items` with RLS;
  interaction kind `quiz_generation` with an optional student reference; models; settings
  `QUIZ_LENGTH`, `QUIZ_STREAK`, `QUIZ_START_LEVEL`

## Phase 3: US1–US2 — Questions

- [x] T005 Prompt `app/prompts/es/quiz_questions.md`; `app/services/quiz_questions.py`
  (retrieve for the topic, ask, validate, store; list, edit, approve, reject); teacher routes

## Phase 4: US3 — Quizzes

- [x] T006 `app/services/quizzes.py` (start, pick, answer, adapt, summary); student routes;
  `openapi.json` exported

## Phase 5: Polish

- [x] T007 Contract note in `specs/001-api-v1-contract/contracts/api.md`; validation against the
  local model (SC-002) in `validation.md`

## Phase 6: Follow-up after the real-stack walkthrough (frontend 008)

- [ ] T008 The quiz level is the difficulty shown; `level_exhausted` changes; no change after the
  last answer (US3 AS1, AS4)
- [ ] T009 Generation asks for a number of questions per level (FR-003)
- [ ] T010 Student quiz topics `GET …/quiz-topics` (US3 AS8, FR-007)
