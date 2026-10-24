---
description: "Task list for 002-consent-and-flags"
---

# Tasks: Study Consent and Course Corrections List

**Input**: [plan.md](plan.md), [spec.md](spec.md), [contracts/api.md](contracts/api.md)

**Tests**: mandatory and first (constitution IV).

## Phase 1: Foundational

- [x] T001 Migration `supabase/migrations/20261024000003_consent.sql` (`consent_events`, index,
  RLS, revoke from client roles) and `ConsentEvent` in `app/models.py`
- [x] T002 `CONSENT_VERSION` setting in `app/core/config.py` and `.env.example`

## Phase 2: US1 — Study consent (P1) 🎯

- [x] T003 [US1] API tests for status, give, revoke, idempotency, version change, history, other
  roles 403, and `consent_required` before allowance and model in `tests/api/test_consent.py`;
  give consent in the shared setup `tests/api/helpers.py`
- [x] T004 [US1] Schemas `app/schemas/consent.py` and service `app/services/consent.py`
- [x] T005 [US1] Router `app/routers/student/consent.py`; consent check in
  `tutor.ensure_can_message`

## Phase 3: US2 + US3 — Flags list and corrected marker (P1)

- [x] T006 [P] [US2] API tests for the course flags list in `tests/api/test_course_flags.py`
- [x] T007 [P] [US3] API tests for `has_correction` and its filter in
  `tests/api/test_course_flags.py`
- [x] T008 [US2] `CourseFlag` schema, `review.list_flags`, `GET /flags` route
- [x] T009 [US3] `has_correction` in summaries and filter

## Phase 4: Polish

- [x] T010 Regenerate `openapi.json`; update the 001 contract doc's error table and the access
  matrix bodies if needed
- [x] T011 Run the full suite and an end-to-end check against the local stack
