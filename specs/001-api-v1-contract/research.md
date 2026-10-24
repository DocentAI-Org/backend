# Research: DocentAI API v1

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-10-24

Each entry records a decision, why it was taken, and what else was considered.

## R1. LLM and embedding access

- **Decision**: one module `app/llm/` with an `LLMClient` protocol (`chat_json`, `embed`) and one
  implementation on the official `openai` SDK pointed at a configurable `LLM_BASE_URL`. Local
  default: Ollama at `http://localhost:11434/v1`. Tests use a deterministic `FakeLLM`.
- **Rationale**: Ollama, OpenAI, Mistral, Gemini, Groq, vLLM and others expose the
  OpenAI-compatible `/chat/completions` and `/embeddings` endpoints, so switching between open and
  closed models is configuration only (constitution V). The SDK gives typed responses with token
  usage, timeouts and retries.
- **Alternatives**: LiteLLM (more providers natively, cost tables, but a large dependency and
  surface); native Ollama client (no closed models); raw httpx (re-implements what the SDK does).

## R2. Models for local development

- **Decision**: chat `qwen2.5:7b` (fallback `qwen2.5:3b` on small machines); embeddings `bge-m3`
  (1024 dimensions, multilingual). Both configurable.
- **Rationale**: material and tutor are in Spanish; bge-m3 is a strong multilingual embedder
  available in Ollama, and qwen2.5 follows JSON-format instructions reliably at small sizes.
- **Alternatives**: `nomic-embed-text` (768 dims, English-centred); `llama3.1:8b` (weaker JSON
  adherence in tests by others; kept as a valid config option).

## R3. Embedding dimension

- **Decision**: fixed at 1024 in the schema (`vector(1024)`), `EMBEDDING_DIMENSIONS=1024` in
  config; the client passes `dimensions` to providers that support it and the app rejects vectors
  of another size at startup check / first use.
- **Rationale**: an HNSW index needs a fixed dimension. 1024 is native for bge-m3 and Mistral,
  and reachable with OpenAI `text-embedding-3-*` via `dimensions`.
- **Alternatives**: untyped `vector` column (no index); one column per provider (YAGNI). Changing
  provider later with a different dimension means a migration and re-embedding, which is acceptable.

## R4. Structured tutor output and grounding

- **Decision**: the tutor prompt lists the retrieved fragments with short IDs (`F1…F4`) and asks
  for JSON `{"kind": "answer"|"hint"|"no_source", "text": str, "cited": ["F1", …]}` using
  `response_format={"type": "json_object"}`. The server maps cited IDs back to fragments; a reply
  with no valid citation, invalid JSON, or `kind="no_source"` is stored as `no_source` with no
  citations (spec edge case).
- **Rationale**: grounding is enforced server-side (constitution I) and does not trust free text.
- **Alternatives**: tool calling (less consistent across small local models); regex citations in
  free text (fragile).

## R5. "Not covered" decision before calling the model

- **Decision**: retrieve top-k (`RETRIEVAL_TOP_K=4`) by cosine similarity over non-excluded
  fragments of validated documents of the course; if none reaches `RETRIEVAL_MIN_SIMILARITY`
  (default 0.55: with bge-m3 on the sample material, covered questions scored ≥ 0.62 and off-topic ones ≤ 0.48; to be re-tuned with the evaluation set), return `no_source` without a model call.
- **Rationale**: FR-053, SC-003; also saves cost.

## R6. Guided mode

- **Decision**: the solution policy is injected into the system prompt. `hints_only` → the model
  must answer problem questions with hints only; `hints_first` → hints unless the request carries
  `request_solution=true`; `direct` → may solve. The model also returns `is_problem`; when the
  policy forbids a solution and the reply is a full `answer` to a problem, the server asks once
  more with a reminder and otherwise replaces it with a fixed hint on the same citations. The server enforces: with `hints_only`, a reply of
  kind `answer` to a request with `request_solution=true` is rejected with
  `solution_not_allowed` before calling the model. `hint_number` = consecutive tutor hints at the end
  of the conversation + 1. Retrieval uses the question alone; only when the last tutor
  reply was a hint does a follow-up also search with the previous question, so "no lo
  entiendo" stays grounded while a new off-topic question is not carried by the last one.
- **Rationale**: the model decides whether the question is a "problem" question; the server owns
  what the policy allows.

## R7. Database access

- **Decision**: SQLAlchemy 2.0 ORM (sync) over psycopg 3, `pgvector` for the vector type. The
  schema is owned by SQL migrations in `supabase/migrations/`; the ORM only maps existing tables
  (no `create_all`, no Alembic).
- **Rationale**: constitution VII (Supabase CLI migrations); the ORM removes boilerplate for ~17
  tables; sync endpoints run in FastAPI's threadpool, which is enough for the pilot scale (≤60
  students) and keeps code simple.
- **Alternatives**: supabase-py/PostgREST (would push authorization into RLS only and lose
  transactions); raw psycopg SQL (more code); async SQLAlchemy (more complexity, no need yet).

## R8. Authentication and roles

- **Decision**: the frontend signs in with Supabase Auth; the API verifies the bearer JWT
  (audience `authenticated`) with `SUPABASE_JWT_SECRET` (HS256) when set, otherwise with the
  project JWKS (`/auth/v1/.well-known/jwks.json`, asymmetric keys). The role comes **only** from
  the `profiles` table, never from token claims or user metadata.
- **Self-registration**: done with Supabase Auth sign-up from the frontend. A database trigger on
  `auth.users` creates the profile with role `student` always.
- **Teacher creation and pseudonymous students**: the API calls the GoTrue admin endpoint
  (`POST /auth/v1/admin/users`, service-role key) and then sets the profile role/pseudonym.
  Pseudonymous accounts use a generated code (e.g. `EST-7K3P9`) and a synthetic email
  `<code>@<PSEUDONYM_EMAIL_DOMAIN>` (default `students.docentai.invalid`) because Supabase Auth
  needs an email or phone; the frontend maps "code + password" to that email at sign-in.
- **Rationale**: role assignment stays server-side (constitution II); no password handling in the
  API.
- **Alternatives**: custom auth (out of scope); role in `app_metadata` (another source of truth).

## R9. File storage

- **Decision**: private bucket `course-material` created in a migration; objects are keyed
  `<course_id>/<document_id>.<ext>` (the uploaded name is display-only, so it cannot address
  other objects); upload and signed URLs
  through the Supabase Storage REST API with httpx and the service-role key, behind a small
  `StorageClient` with an in-memory fake for tests.
- **Rationale**: constitution VII and §4.2; avoids the supabase-py dependency.

## R10. Document processing

- **Decision**: FastAPI `BackgroundTasks` after the upload response. Parsing: `pypdf` (one section
  per page, label `p. N`), `python-docx` (sections by heading, label `§ <heading>`), Markdown split
  by headings without extra dependency. Chunking: paragraphs merged up to ~1,200 characters with no
  cross-section merging; each fragment keeps its section and location label. Then embeddings in
  batches. On any failure: `processing_status=error` with reason (`unsupported_format`,
  `no_readable_text`, `processing_failed`). On startup, documents left in `processing` are marked
  `error/processing_interrupted` so the teacher can re-upload.
- **Rationale**: constitution VIII (no queue service); pilot volumes are small.
- **Alternatives**: a job queue (Celery/RQ/Vercel Queues): extra service, not justified yet.

## R11. Daily allowance under concurrency

- **Decision**: table `daily_usage(student_id, usage_date, used)`; a single atomic statement
  `INSERT … ON CONFLICT (student_id, usage_date) DO UPDATE SET used = daily_usage.used + 1 WHERE
  daily_usage.used < :limit RETURNING used` reserves one message **before** the model call, in its
  own committed transaction; a failed call releases it (`used = used - 1`). `usage_date` is the
  date in `DAILY_RESET_TIMEZONE` (default `Europe/Madrid`).
- **Rationale**: SC-007 and FR-061 without locks held during the slow model call.

## R12. Cost and interaction log

- **Decision**: `estimated_cost_usd = in_tokens × LLM_PRICE_INPUT_PER_MTOK / 1e6 + out_tokens ×
  LLM_PRICE_OUTPUT_PER_MTOK / 1e6` (both 0 for Ollama). The student reference stored in
  `interaction_logs` is `HMAC-SHA256(LOG_PSEUDONYM_SECRET, student_id)`; erasure recomputes it to
  delete the student's rows. Prompts sent to the model contain no names, emails or IDs.
- **Rationale**: P2, constitution V and VI.

## R13. API shape

- **Decision**: role-scoped routers under `/v1`: `/v1/admin/*`, `/v1/teacher/*`,
  `/v1/student/*`, plus `/v1/me` and `/v1/health`. Each router has one role dependency. Lists use
  `limit`/`offset` and return `{items, total, limit, offset}`. Errors use
  `{"error": {"code", "message", "details"}}`, where `message` is developer-facing English. Stub
  endpoints carry `x-stub: true` in OpenAPI and say so in their description.
- **Rationale**: mirrors the frontend's role route groups (frontend constitution II) and makes the
  authorization rule of each endpoint obvious; distinct response models per role avoid union types
  in the generated client.
- **Alternatives**: one resource tree with role-dependent response bodies (unions, easy to leak a
  field to the wrong role).

## R14. OpenAPI snapshot

- **Decision**: `scripts/export_openapi.py` writes `openapi.json` at the repository root; a
  contract test fails when `app.openapi()` differs from the committed file.
- **Rationale**: constitution III.

## R15. Test database

- **Decision**: API and integration tests run against the local Supabase Postgres
  (`npx supabase db start` / `supabase start`, port 54322) with migrations applied. Each test runs
  inside an outer transaction rolled back at the end (SQLAlchemy `join_transaction_mode=
  "create_savepoint"`); the allowance concurrency test uses real commits and cleans up. Unit tests
  (parsing, chunking, prompts, cost, JWT) need no database. Tests mint their own JWTs with a test
  HS256 secret and insert users directly into `auth.users`.
- **Rationale**: same database engine and extensions as production (constitution VII); fast and
  isolated.
- **Alternatives**: SQLite (no pgvector, no RLS); testcontainers (another dependency, and would
  not include the Supabase `auth`/`storage` schemas).

## R16. Row Level Security

- **Decision**: every table has RLS enabled and **no** policy for `anon`/`authenticated`, and
  privileges on application tables are revoked from those roles: the API (connecting as the
  database owner) is the only access path in v1. Policies are added in the migration of any future
  feature that grants direct client access.
- **Rationale**: defense in depth (constitution II, VII): a leaked anon key exposes nothing.

## R17. Exercise feedback stub (Story 7)

- **Decision**: the endpoint performs every real step except the model call — validation,
  allowance reservation, retrieval-based citations, storage of submission and learning-record
  entry, interaction log with zero tokens — and returns fixed feedback (`verdict=incorrect`,
  `mistake_location="Paso 1"`, `error_type="placeholder"`, first course topic or none). It is marked
  `x-stub: true`.
- **Rationale**: FR-100; the error taxonomy (requirements §5) is not defined.

## R18. New dependencies (constitution VIII)

| Dependency | Why |
|---|---|
| `openai` | OpenAI-compatible client for every provider (R1) |
| `sqlalchemy`, `psycopg[binary]`, `pgvector` | Database access and vector type (R7) |
| `pyjwt[crypto]` | Supabase JWT verification, HS256 and JWKS (R8) |
| `httpx` (moved from dev to main) | Supabase Auth admin and Storage REST calls (R8, R9) |
| `python-multipart` | FastAPI file uploads |
| `pypdf`, `python-docx` | PDF and DOCX text extraction (R10) |
