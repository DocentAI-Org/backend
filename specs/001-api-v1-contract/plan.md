# Implementation Plan: DocentAI API v1 — Contract for the MVP "Must" Requirements

**Branch**: `001-api-v1-contract` | **Date**: 2026-10-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-api-v1-contract/spec.md`

## Summary

Turn the FastAPI skeleton into the versioned DocentAI API (`/v1`) covering every M requirement:
Supabase Auth–verified identity with roles from a `profiles` table, role-scoped routers
(admin / teacher / student), courses and class-code enrolment, material upload to a private
bucket with background parsing, chunking and embedding into pgvector, teacher validation and
fragment exclusion, tutor settings, topics, a grounded tutor chat that retrieves only validated
fragments and returns structured citations (or `no_source` without calling the model), an atomic
per-student daily allowance, a cost-aware interaction log, teacher review and corrections, and a
contract-honoring stub for exercise feedback. All model calls go through one OpenAI-compatible
client configured by environment (Ollama locally). The generated `openapi.json` is committed and
checked in CI.

## Technical Context

**Language/Version**: Python ≥ 3.11 (as declared in `pyproject.toml`; local venv 3.11)

**Primary Dependencies**: FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (sync) + psycopg 3,
pgvector, openai SDK, PyJWT[crypto], httpx, python-multipart, pypdf, python-docx — justified in
[research.md R18](research.md#r18-new-dependencies-constitution-viii)

**Storage**: Supabase PostgreSQL 15+ with pgvector (schema via `supabase/migrations/`), Supabase
Storage private bucket `course-material`, Supabase Auth

**Testing**: pytest + FastAPI TestClient; unit tests without network or DB; API tests against the
local Supabase Postgres with per-test rollback; `FakeLLM`, fake storage and fake auth-admin
clients; OpenAPI snapshot test

**Target Platform**: Linux container (local Docker; Railway EU from December 2026)

**Project Type**: web service (REST API)

**Performance Goals**: tutor reply < 10 s p95 on local hardware (SC-008); other endpoints
< 300 ms p95 locally

**Constraints**: zero cost locally; no identifying data sent to the model; per-student daily
limit enforced under concurrency; only validated, non-excluded fragments retrievable

**Scale/Scope**: pilot ≤ 60 students × ≤ 15 messages/day, a few teachers, tens of documents;
~55 endpoints, 16 tables

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-research | Post-design | Evidence |
|---|---|---|---|
| I. Grounded, teacher-controlled answers | ✅ | ✅ | Retrieval filter (data-model › fragments), `no_source` before model call (R5), server-side citation mapping (R4), settings applied server-side (R6), corrections linked to messages (teacher_flags) |
| II. Backend-enforced authorization | ✅ | ✅ | JWT verified every request, role from `profiles` only (R8); role-scoped routers (R13); ownership → 404; access-matrix tests (SC-002); RLS on, no client policies (R16) |
| III. Contract-first API | ✅ | ✅ | `/v1`, named Pydantic models, single error schema with codes (contracts/api.md), committed `openapi.json` + check (R14), `x-stub` marking (R17) |
| IV. Test-first | ✅ | ✅ | tasks.md orders tests before code per story; FakeLLM, no network in tests (R15); every acceptance scenario has an API test |
| V. Provider-agnostic LLM & cost | ✅ | ✅ | single `app/llm` module, config-only provider (R1), Ollama default (R2), interaction log with tokens/latency/cost (R12), atomic allowance before call (R11), lean context settings, prompts delimit data (R4) |
| VI. Privacy by design | ✅ | ✅ | pseudonymous accounts (R8), HMAC student ref in logs (R12), no names/emails in prompts, no message contents in log output; Sentry deferred to deployment (out of scope) |
| VII. Versioned data | ✅ | ✅ | Supabase CLI migrations with RLS, private bucket + signed URLs (R9), standard Postgres + pgvector |
| VIII. Simplicity | ✅ | ✅ | one service, BackgroundTasks instead of a queue (R10), dependencies justified (R18); fakes for external services are test seams, not new abstractions (see below) |

No violations. `StorageClient` and `AuthAdminClient` are thin wrappers around two Supabase REST
endpoints each; they exist because the code must call those services and tests must not.

## Project Structure

### Documentation (this feature)

```text
specs/001-api-v1-contract/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/api.md     # Phase 1
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
app/
├── main.py                  # app factory, routers, error handlers, startup recovery
├── core/
│   ├── config.py            # Settings (all env vars)
│   ├── db.py                # engine, session factory, get_session dependency
│   ├── errors.py            # ApiError, error schema, exception handlers
│   ├── security.py          # JWT verification, CurrentUser, role dependencies
│   └── pagination.py        # Page[T], PageParams
├── models.py                # SQLAlchemy ORM mappings of the migration tables
├── schemas/                 # Pydantic request/response models per area
│   ├── common.py  me.py  admin.py  courses.py  documents.py  topics.py
│   ├── tutor.py  chat.py  exercises.py  review.py
├── llm/
│   ├── client.py            # LLMClient protocol, OpenAICompatClient, get_llm dependency
│   └── prompts.py           # loads app/prompts/<lang>/*.md
├── prompts/es/              # tutor_system.md, policies.md, messages.md
├── integrations/
│   ├── storage.py           # Supabase Storage (upload, signed URL, delete)
│   └── auth_admin.py        # Supabase Auth admin (create user)
├── services/
│   ├── accounts.py  courses.py  documents.py  parsing.py  chunking.py
│   ├── retrieval.py  tutor.py  allowance.py  interactions.py
│   ├── topics.py  review.py  exercises.py
└── routers/
    ├── health.py  me.py  admin.py
    ├── teacher/  courses.py  settings.py  documents.py  topics.py  review.py
    └── student/  courses.py  chat.py  exercises.py

supabase/
├── config.toml
└── migrations/               # 2026102400000x_*.sql

scripts/
├── export_openapi.py         # writes/checks openapi.json
└── seed_dev.py               # local demo users and tokens

tests/
├── conftest.py               # settings, DB rollback fixture, users, tokens, client
├── fakes.py                  # FakeLLM, FakeStorage, FakeAuthAdmin
├── fixtures/                 # ecuaciones.md, sample.pdf, sample.docx
├── unit/                     # parsing, chunking, jwt, cost, prompts, grounding
├── api/                      # one module per user story + access matrix
└── contract/                 # openapi snapshot

openapi.json
.github/workflows/ci.yml
```

**Structure Decision**: single FastAPI service in the existing `app/` package, extended with the
layout above. The existing `/health` and `/chat` routers are replaced by `/v1/health` and the
student chat (spec Assumptions).

## Complexity Tracking

No constitution violations to justify.
