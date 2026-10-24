---
description: "Task list for 001-api-v1-contract"
---

# Tasks: DocentAI API v1 — Contract for the MVP "Must" Requirements

**Input**: Design documents from `specs/001-api-v1-contract/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/api.md](contracts/api.md)

**Tests**: Mandatory (constitution IV). In every story, test tasks come first and MUST be seen
failing before the implementation tasks.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1–US8 from spec.md

---

## Phase 1: Setup

- [x] T001 Add dependencies from research R18 to `pyproject.toml` (move httpx to main), add pytest
  marker `db`, run `uv lock`
- [x] T002 [P] Initialise Supabase project config in `supabase/config.toml` (project id
  `docentai-backend`, storage enabled, auth email auto-confirm for local)
- [x] T003 [P] Rewrite `.env.example` with every setting from research (DB, Supabase, LLM, limits,
  retrieval, secrets) and drop `OPENAI_API_KEY`
- [x] T004 [P] Add test fixtures `tests/fixtures/ecuaciones.md`, `tests/fixtures/sample.pdf`,
  `tests/fixtures/sample.docx` (generated, no personal data)

---

## Phase 2: Foundational (blocks every story)

- [x] T005 Migration `supabase/migrations/20261024000001_schema.sql`: extensions (`vector`,
  `pgcrypto`), all tables, constraints and indexes from data-model.md, HNSW index on
  `fragments.embedding`
- [x] T006 Migration `supabase/migrations/20261024000002_security.sql`: RLS on every table, revoke
  from `anon`/`authenticated`, `handle_new_user` trigger on `auth.users` (role student), private
  bucket `course-material`
- [x] T007 [P] Settings in `app/core/config.py` (all env vars, defaults per research)
- [x] T008 [P] Error schema, `ApiError` and handlers (HTTPException, validation) in
  `app/core/errors.py`
- [x] T009 [P] `Page[T]` and pagination params in `app/core/pagination.py`
- [x] T010 Engine, session factory and `get_session` dependency in `app/core/db.py`
- [x] T011 ORM mappings for every table in `app/models.py`
- [x] T012 [P] `LLMClient` protocol, `OpenAICompatClient` (chat JSON + embeddings + usage) and
  `get_llm` dependency in `app/llm/client.py`; prompt loader in `app/llm/prompts.py`
- [x] T013 [P] `StorageClient` in `app/integrations/storage.py`, `AuthAdminClient` in
  `app/integrations/auth_admin.py`, with dependencies
- [x] T014 Test harness: `tests/fakes.py` (FakeLLM with deterministic hashed embeddings, FakeStorage,
  FakeAuthAdmin), `tests/conftest.py` (DB rollback session, user factory inserting into
  `auth.users`, JWT minting, TestClient with overrides; fails clearly when DB is down)
- [x] T015 [P] Unit test for errors and pagination in `tests/unit/test_core.py`
- [x] T016 App factory in `app/main.py`: `/v1` routers, error handlers, CORS; remove old
  `app/routers/chat.py` and `/health`
- [x] T017 [P] `scripts/export_openapi.py` (write / `--check`) and contract test
  `tests/contract/test_openapi_snapshot.py`
- [x] T018 Health: test `tests/api/test_health.py` (replaces `tests/test_health.py`), then
  `app/routers/health.py` with DB and LLM checks

**Checkpoint**: migrations apply, `uv run pytest` runs green on the harness.

---

## Phase 3: US1 — Authentication and role-limited access (P1) 🎯

**Goal**: every request authenticated; roles from `profiles`; admin minimal.
**Independent test**: access matrix across admin, two teachers, two students.

- [x] T019 [P] [US1] Unit tests for JWT verification (HS256 valid/expired/wrong audience; JWKS
  path) in `tests/unit/test_security.py`
- [x] T020 [P] [US1] API tests for `/v1/me` (get, patch language, 401 without token, disabled
  account 403) and self-registration trigger in `tests/api/test_us1_auth.py`
- [x] T021 [P] [US1] API tests for admin endpoints (users list, create teacher, pseudonymous batch,
  courses list, 403 for non-admins) in `tests/api/test_us1_admin.py`
- [x] T022 [US1] `app/core/security.py`: token verification, `CurrentUser`, `require_role`
- [x] T023 [US1] Schemas `app/schemas/me.py`, `app/schemas/admin.py`
- [x] T024 [US1] `app/services/accounts.py` (create teacher, pseudonymous batch, code generation)
- [x] T025 [US1] Routers `app/routers/me.py`, `app/routers/admin.py` (evaluation-set endpoint wired
  in US8)

---

## Phase 4: US2 — Courses and class-code enrolment (P1)

**Goal**: teachers create courses; students join with codes.
**Independent test**: create, join, list, regenerate/disable code.

- [x] T026 [P] [US2] API tests for teacher course CRUD, code regenerate/disable, students list,
  revoke in `tests/api/test_us2_courses.py`
- [x] T027 [P] [US2] API tests for student join (valid, invalid, disabled, idempotent, revoked) and
  course list/detail in `tests/api/test_us2_enrolment.py`
- [x] T028 [US2] Schemas `app/schemas/courses.py`
- [x] T029 [US2] `app/services/courses.py` (create with tutor settings row, ownership lookups, code
  generation, enrolment)
- [x] T030 [US2] Routers `app/routers/teacher/courses.py`, `app/routers/student/courses.py`

---

## Phase 5: US3 — Material upload, processing and validation (P1)

**Goal**: upload → fragments with embeddings → teacher validation/exclusion.
**Independent test**: upload fixture, wait ready, exclude fragment, validate, check retrievable set.

- [x] T031 [P] [US3] Unit tests for parsing (PDF pages, DOCX headings, Markdown headings, no text)
  and chunking (size bound, sections preserved, labels) in `tests/unit/test_parsing.py`,
  `tests/unit/test_chunking.py`
- [x] T032 [P] [US3] API tests for upload (202, type/size errors), processing to ready/error,
  fragments list/exclude, validate/exclude document, `document_not_ready`, delete, signed URL in
  `tests/api/test_us3_material.py`
- [x] T033 [US3] `app/services/parsing.py` and `app/services/chunking.py`
- [x] T034 [US3] Schemas `app/schemas/documents.py`
- [x] T035 [US3] `app/services/documents.py` (store, process in background with embeddings,
  validation transitions, startup recovery of interrupted documents)
- [x] T036 [US3] `app/services/retrieval.py` (top-k cosine over retrievable fragments with
  threshold) with API-level test of the filter in `tests/api/test_us3_material.py`
- [x] T037 [US3] Router `app/routers/teacher/documents.py`

---

## Phase 6: US4 — Grounded tutor chat, allowance and interaction log (P1)

**Goal**: cited answers, `no_source`, hints, daily limit, logs.
**Independent test**: seeded validated document + FakeLLM.

- [x] T038 [P] [US4] Unit tests for tutor reply parsing/grounding (valid JSON, unknown IDs,
  invalid JSON → `no_source`), prompt building without identifying data, cost estimate in
  `tests/unit/test_tutor.py`
- [x] T039 [P] [US4] API tests for disclosure, conversations, answer with citations, `no_source`
  without model call, hints and `solution_not_allowed`, provider failure + retry, student reads
  settings, citation availability after exclusion in `tests/api/test_us4_chat.py`
- [x] T040 [P] [US4] API tests for allowance (read, limit reached with `resets_at`, failed not
  counted) and concurrency (10 parallel reservations with real commits) in
  `tests/api/test_us4_allowance.py`
- [x] T041 [P] [US4] API test that every tutor reply writes an interaction log with tokens,
  latency, cost and HMAC student ref in `tests/api/test_us4_logging.py`
- [x] T042 [US4] Prompts `app/prompts/es/tutor_system.md`, `app/prompts/es/policies.md`,
  `app/prompts/es/messages.md`
- [x] T043 [US4] `app/services/allowance.py` (reserve/release/read, timezone reset)
- [x] T044 [US4] `app/services/interactions.py` (log writer, HMAC ref, cost)
- [x] T045 [US4] `app/services/tutor.py` (history, retrieval, prompt, JSON reply, grounding,
  hint numbering, persistence)
- [x] T046 [US4] Schemas `app/schemas/chat.py`, `app/schemas/tutor.py` (student settings view)
- [x] T047 [US4] Router `app/routers/student/chat.py` (+ settings read and disclosure in
  `app/routers/student/courses.py`)

---

## Phase 7: US5 — Tutor settings (P2)

- [x] T048 [P] [US5] API tests for defaults, update, validation error, and policy applied to next
  reply in `tests/api/test_us5_settings.py`
- [x] T049 [US5] Router `app/routers/teacher/settings.py` (schemas in `app/schemas/tutor.py`)

---

## Phase 8: US6 — Topics and assignments (P2)

- [x] T050 [P] [US6] API tests for topic CRUD, uniqueness, reorder, assignments (confirmed,
  suggested → confirmed/changed/removed), delete topic keeps learning-record name, unassigned
  material in `tests/api/test_us6_topics.py`
- [x] T051 [US6] Schemas `app/schemas/topics.py`
- [x] T052 [US6] `app/services/topics.py`
- [x] T053 [US6] Router `app/routers/teacher/topics.py`; document `topics` field filled in
  `app/services/documents.py`

---

## Phase 9: US7 — Exercise submission (stub) and learning record (P2)

- [x] T054 [P] [US7] API tests for submission (stub feedback, citations, saved learning-record
  entry, allowance and log), lists, learning record visibility (student, teacher, others 404),
  `x-stub` in OpenAPI in `tests/api/test_us7_exercises.py`
- [x] T055 [US7] Schemas `app/schemas/exercises.py`
- [x] T056 [US7] `app/services/exercises.py` (stub per research R17)
- [x] T057 [US7] Router `app/routers/student/exercises.py`; teacher learning-record endpoint in
  `app/routers/teacher/review.py`

---

## Phase 10: US8 — Review and corrections (P2)

- [x] T058 [P] [US8] API tests for conversation list/filters/detail, submissions list, flag
  upsert/delete on messages and submissions, student sees correction without category,
  `not_a_tutor_message`, admin evaluation set in `tests/api/test_us8_review.py`
- [x] T059 [US8] Schemas `app/schemas/review.py`
- [x] T060 [US8] `app/services/review.py`
- [x] T061 [US8] Router `app/routers/teacher/review.py`; `GET /v1/admin/evaluation-set` in
  `app/routers/admin.py`

---

## Phase 11: Polish & cross-cutting

- [x] T062 [P] Access matrix test over every route × role × own/other in
  `tests/api/test_access_matrix.py` (SC-002)
- [x] T063 [P] `scripts/seed_dev.py` for local demo users and tokens
- [x] T064 [P] CI workflow `.github/workflows/ci.yml` (uv, ruff, format, OpenAPI check, Supabase DB,
  pytest)
- [x] T065 Regenerate and commit `openapi.json`
- [x] T066 [P] Update `README.md` (backend) and workspace `README.md` backend section to the uv +
  Supabase + Ollama flow
- [x] T067 Run quickstart.md end to end against local Supabase and Ollama; record results in
  `specs/001-api-v1-contract/validation.md`
- [x] T068 Fix the findings of the independent code review (see `validation.md`)

---

## Dependencies

- Setup → Foundational → US1 → US2 → US3 → US4. US5 and US6 need US2 (US5 also checks US4's
  policy use). US7 needs US3 + US4 (retrieval, allowance, logs). US8 needs US4 and US7.
- Polish after all stories.

## Parallel examples

- Foundational: T007, T008, T009, T012, T013 together; then T010 → T011 → T014.
- US3: T031 and T032 together (tests), then T033 and T034 together.
- US4: T038, T039, T040, T041 together (tests).

## Implementation strategy

MVP = Phases 1–6 (core loop: sign in → course → validated material → grounded answer). Then US5,
US6, US7, US8, each independently testable, then polish. Commit per task group, referencing task
IDs (`feat(chat): T045 …`).
