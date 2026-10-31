# Tasks: Targeted Help for Repeated Mistakes

**Spec**: [spec.md](spec.md)

## Phase 1: Tests first

- [x] T001 [P] API tests: US1 AS1–AS5 in `tests/api/test_repeated_mistakes.py`
- [x] T002 [P] API tests: US2 AS1–AS8 in `tests/api/test_mistake_review.py` (fake model)
- [x] T003 [P] Unit tests: review reply validation in `tests/unit/test_mistake_review.py`

## Phase 2: Data

- [x] T004 Migration: `mistake_reviews` (+ citations link) with RLS; interaction kind `review`;
  model `MistakeReview`; settings `REPEATED_MISTAKE_COUNT`, `REPEATED_MISTAKE_DAYS`

## Phase 3: US1 — Pattern

- [x] T005 `repeated_mistake` in the submission views (student and teacher)

## Phase 4: US2 — Review

- [x] T006 Prompt `app/prompts/es/mistake_review.md`; `app/services/reviews.py` (retrieve, ask,
  validate, store, charge/release); routes; `openapi.json` exported

## Phase 5: Polish

- [x] T007 Contract note in `specs/001-api-v1-contract/contracts/api.md`; validation against the
  local model (SC-002) in `validation.md`
