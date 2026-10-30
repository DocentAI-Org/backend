# Validation: teacher dashboard (T007)

**Date**: 2026-10-30 · **Branch**: `004-teacher-dashboard`

## SC-001 — Acceptance scenarios

Every scenario of US1–US3 has an API test (`tests/api/test_teacher_dashboard.py`,
`tests/api/test_risk.py`) and the criteria have unit tests (`tests/unit/test_risk.py`): 22 new
tests; the full suite passes (191).

## SC-002 — Response time

Local Supabase, one course with 30 active students, 6 topics, 600 messages and 1,000 exercises
with their learning-record entries spread over 50 days (seeded in a rolled-back transaction, not
committed), 5 runs per period, service call without HTTP:

| Request | Median | Max |
|---|---|---|
| Dashboard `7d` | 8 ms | 15 ms |
| Dashboard `30d` | 9 ms | 11 ms |
| Dashboard `all` | 9 ms | 12 ms |
| Student risk | 5 ms | — |

Well under the 300 ms target. The dashboard runs a fixed number of queries whatever the number
of students (FR-007).

## Notes

- Weeks and "days inactive" are computed in UTC; for a Spanish course a late-evening activity can
  fall on the next day. Acceptable for the provisional criteria; revisit if the educational stream
  needs calendar days in local time.
