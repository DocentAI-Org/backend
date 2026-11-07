# Validation: Student Erasure on Request

**Date**: 2026-11-07 · **Stack**: local Supabase (CLI, real Auth), API on port 8077, `seed_dev.py` users.

The API tests (`tests/api/test_student_erasure.py`, 7 passed; full suite 355 passed) use a fake
auth client. This run checks the real Supabase Auth admin call.

| Check | Result |
|---|---|
| Admin erases a new pseudonymous student | 200; `auth.users`, `auth.identities` and `profiles` rows gone |
| Two interaction logs inserted under the student's `student_ref` | `interaction_logs: 2` in the response, 0 rows left |
| Logs deleted in the open transaction while Auth deletes the account | no lock wait (61 ms) |
| Second erasure | 404 `not_found` |
| Erasing a teacher | 409 `not_a_student`, nothing deleted |
| A teacher calls the endpoint | 403 `forbidden` |

Not checked on the real stack: an Auth outage (covered by the fake, 503 and nothing deleted).
