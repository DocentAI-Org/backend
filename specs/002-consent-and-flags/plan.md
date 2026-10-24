# Implementation Plan: Study Consent and Course Corrections List

**Branch**: `002-consent-and-flags` | **Date**: 2026-10-24 | **Spec**: [spec.md](spec.md)

## Summary

Additive changes to the API v1: an append-only `consent_events` table with student endpoints to
read, give and revoke study consent (checked before any tutor or exercise request), a teacher
endpoint listing a course's flags, and a `has_correction` field and filter on conversation
summaries. No new dependencies.

## Technical Context

Same as [001 plan](../001-api-v1-contract/plan.md): Python, FastAPI, SQLAlchemy over Supabase
Postgres, pytest against the local stack. New setting `CONSENT_VERSION` (default `2026-10`).

## Decisions

- **Consent model**: append-only events (`given` / `revoked`, version, time) instead of columns on
  `profiles`, so the history required as proof of consent is never overwritten. Current status =
  latest event; "given" only if its version equals `CONSENT_VERSION`.
- **Enforcement point**: `tutor.ensure_can_message` (shared by messages, retries and exercise
  submissions), before the allowance is reserved (FR-004, SC-001).
- **Idempotency**: giving consent when already given for the current version, or revoking when
  not given, records nothing and returns the current status.
- **Flags list**: one query over `teacher_flags` of the course; the student, original text and
  link target come from the message (→ conversation) or the submission.
- **`has_correction`**: `EXISTS` over flags joined to the conversation's messages, like
  `has_no_source`.

## Constitution Check

| Principle | Pre | Post | Note |
|---|---|---|---|
| I. Grounded answers | ✅ | ✅ | Unchanged |
| II. Authorization | ✅ | ✅ | Consent endpoints student-only and self-only; flags list owner-only; access matrix covers the new routes automatically |
| III. Contract-first | ✅ | ✅ | Additive; `openapi.json` regenerated; new error code `consent_required` |
| IV. Test-first | ✅ | ✅ | Tests per acceptance scenario before code |
| V. LLM & cost | ✅ | ✅ | Consent checked before the allowance and the model |
| VI. Privacy | ✅ | ✅ | Consent history is the proof required by §4.1; no PII added |
| VII. Versioned data | ✅ | ✅ | Migration `20261024000003_consent.sql` with RLS |
| VIII. Simplicity | ✅ | ✅ | No new dependency or service |

## Project Structure

```text
supabase/migrations/20261024000003_consent.sql
app/models.py                       # ConsentEvent
app/schemas/consent.py              # Consent, ConsentEvent
app/services/consent.py
app/routers/student/consent.py
app/services/tutor.py               # consent check in ensure_can_message
app/schemas/review.py, app/services/review.py, app/routers/teacher/review.py  # flags, has_correction
tests/api/test_consent.py, tests/api/test_course_flags.py
```

## Complexity Tracking

None.
