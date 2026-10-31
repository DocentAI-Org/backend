# Tasks: Pre-test and Post-test

**Spec**: [spec.md](spec.md)

## Phase 1: Tests first

- [x] T001 [P] API tests: US1 AS1–AS5, US2 AS1–AS3 in `tests/api/test_course_test_setup.py`
- [x] T002 [P] API tests: US3 AS1–AS6, US4 AS1–AS2 in `tests/api/test_course_test_taking.py`

## Phase 2: Data

- [x] T003 Migration: `test_questions`, `test_phases`, `test_attempts`, `test_answers` with RLS;
  models

## Phase 3: US1–US4

- [x] T004 `app/services/course_tests.py`; schemas; teacher routes (questions, phases, results)
- [x] T005 Student routes (phases, questions, submission); `openapi.json` exported

## Phase 4: Polish

- [x] T006 Contract note in `specs/001-api-v1-contract/contracts/api.md`
