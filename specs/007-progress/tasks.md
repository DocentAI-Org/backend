# Tasks: Progress and Mastery by Topic

**Spec**: [spec.md](spec.md)

## Phase 1: Tests first

- [x] T001 [P] API tests: US1 AS1–AS8, US2 AS1–AS3 in `tests/api/test_progress.py`; correct
  exercises with a topic in `tests/api/test_us7_exercises.py`
- [x] T002 [P] Unit tests: score, levels and history in `tests/unit/test_progress.py`; topic of
  correct feedback in `tests/unit/test_exercise_feedback.py`

## Phase 2: US1–US2

- [x] T006 Exercise feedback classifies the topic of correct exercises (FR-005)
- [x] T003 Settings `PROGRESS_WINDOW`, `PROGRESS_MIN_ITEMS`, `PROGRESS_PROGRESSING`,
  `PROGRESS_MASTERED`; `app/services/progress.py`; schemas; student and teacher routes
- [x] T004 `quizzes` in the weekly activity (spec 004); `openapi.json` exported

## Phase 3: Polish

- [x] T005 Contract note in `specs/001-api-v1-contract/contracts/api.md`
