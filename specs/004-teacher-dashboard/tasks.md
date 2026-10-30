# Tasks: Teacher Dashboard — Recurring Errors and At-Risk Students

**Spec**: [spec.md](spec.md) · **Criteria**: [risk-criteria.md](risk-criteria.md)

## Phase 1: Tests first

- [ ] T001 [P] API tests: US1 AS1–AS5 in `tests/api/test_teacher_dashboard.py`
- [ ] T002 [P] API tests: US2 AS1–AS5, US3 AS1 in `tests/api/test_risk.py`
- [ ] T003 [P] Unit tests: criteria evaluation and edge cases in `tests/unit/test_risk.py`

## Phase 2: Data

- [ ] T004 Migration: `risk_criteria` table with the provisional v0 seed and RLS; model
  `RiskCriterion`

## Phase 3: US1–US2 — Dashboard and risk

- [ ] T005 `app/services/dashboard.py`: error aggregates by topic and student, activity counts,
  `enough_data`, criteria evaluation (set-based queries)
- [ ] T006 Routes `GET …/dashboard`, `GET …/students/{id}/risk`, `GET /v1/teacher/risk-criteria`;
  schemas; `openapi.json` exported

## Phase 4: Polish

- [ ] T007 Contract note in `specs/001-api-v1-contract/contracts/api.md`; seed script for 30
  students and the SC-002 timing in `validation.md`
