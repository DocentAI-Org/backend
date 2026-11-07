# Tasks: Student Erasure on Request

**Spec**: [spec.md](spec.md)

- [ ] T001 Tests first: erasure of every linked row and the interaction logs, other students
  untouched, old token 401, second erasure 404, teacher or admin 409, roles 403, auth failure
  503 (`tests/api/test_student_erasure.py`)
- [ ] T002 `AuthAdminClient.delete_user` (Supabase and the test fake)
- [ ] T003 [US1] [US2] `app/services/erasure.py`; `DELETE /v1/admin/students/{student_id}`
- [ ] T004 Contract note and `openapi.json`
