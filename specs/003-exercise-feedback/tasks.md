# Tasks: Real Exercise Feedback with a Provisional Error Taxonomy

**Spec**: [spec.md](spec.md) · **Taxonomy**: [taxonomy.md](taxonomy.md)

## Phase 1: Tests first

- [ ] T001 [P] API tests: US1 AS1–AS6, US2 AS1–AS2 in `tests/api/test_us7_exercises.py` (fake model)
- [ ] T002 [P] API test: US3 AS1 in `tests/api/test_error_types.py`
- [ ] T003 [P] Unit tests: reply validation in `tests/unit/test_exercise_feedback.py`

## Phase 2: Data

- [ ] T004 Migration: `error_types` table with the provisional v0 seed and RLS; `not_assessed`
  verdict; model `ErrorType`

## Phase 3: US1–US2 — Feedback

- [ ] T005 Prompt `app/prompts/es/exercise_feedback.md`; `build_feedback_messages`
- [ ] T006 `validate_feedback()` and the new `submit()` in `app/services/exercises.py`; provider
  failure → 503 with the allowance released

## Phase 4: US3 — Taxonomy endpoint

- [ ] T007 `GET /v1/error-types`; schemas; `openapi.json` exported

## Phase 5: Polish

- [ ] T008 Contract note in `specs/001-api-v1-contract/contracts/api.md`; validation against the
  local model (SC-002) in `validation.md`
