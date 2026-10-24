# Quickstart: DocentAI API v1 (local, zero cost)

**Feature**: [spec.md](spec.md) · **Contract**: [contracts/api.md](contracts/api.md)

Validates SC-005: from a fresh clone to a cited answer in under 15 minutes.

## Prerequisites

- Docker Desktop (or OrbStack) running
- Node.js LTS (for `npx supabase`) or the Supabase CLI installed
- `uv`
- Ollama running (`ollama serve`) with the models from research R2:

```bash
ollama pull qwen2.5:7b
ollama pull bge-m3
```

## 1. Start the local stack

```bash
cd backend
uv sync
npx supabase start            # Postgres + pgvector, Auth, Storage; applies supabase/migrations
npx supabase status -o env    # copy API_URL, SERVICE_ROLE_KEY, JWT_SECRET, DB_URL into .env
cp .env.example .env          # then fill the values above
uv run uvicorn app.main:app --reload
```

Expected: `GET http://localhost:8000/v1/health` → `{"status": "ok", "database": "ok", "llm": "ok", …}`.

## 2. Seed demo users

```bash
uv run python scripts/seed_dev.py
```

Creates an admin, a teacher and a student in local Supabase Auth and prints their credentials and
a ready-to-use access token for each (local development only).

## 3. Walk through the core loop

With `$TEACHER` and `$STUDENT` set to the printed tokens (see `scripts/seed_dev.py --help`):

1. Teacher creates a course: `POST /v1/teacher/courses {"name": "Álgebra"}` → note `class_code`.
2. Teacher uploads `tests/fixtures/ecuaciones.md`: `POST /v1/teacher/courses/{id}/documents`
   (multipart) → `202`, `processing_status: "processing"`.
3. Poll `GET …/documents/{doc}` until `ready`; list `…/fragments`.
4. Validate: `POST …/documents/{doc}/validate` → `validation_status: "validated"`.
5. Student joins: `POST /v1/student/enrolments {"class_code": "…"}`, then
   `POST /v1/student/courses/{id}/disclosure`.
6. Student opens a conversation and asks "¿Cómo despejo la x en 2x + 3 = 7?" → `tutor_message`
   has `kind` `answer` or `hint` and at least one citation to `ecuaciones.md`.
7. Student asks "¿Quién ganó el mundial de 2010?" → `kind: "no_source"`, no citations.
8. `GET /v1/student/allowance` → `used` is 2 (or the number of messages sent).

The interactive docs at `http://localhost:8000/docs` cover the same flow.

## 4. Automated checks (what CI runs)

```bash
npx supabase db start                   # DB only is enough for tests
uv run ruff check . && uv run ruff format --check .
uv run python scripts/export_openapi.py --check
uv run pytest                           # unit + API + contract; fake LLM, no network
```

Unit tests alone (no database): `uv run pytest -m "not db"`.

## 5. Switch provider (SC-006)

Change only `.env`, e.g. a hosted OpenAI-compatible provider:

```env
LLM_BASE_URL=https://api.mistral.ai/v1
LLM_API_KEY=…
LLM_CHAT_MODEL=mistral-small-latest
LLM_EMBEDDING_MODEL=mistral-embed
LLM_PRICE_INPUT_PER_MTOK=0.1
LLM_PRICE_OUTPUT_PER_MTOK=0.3
```

Re-run the health check and step 3.6. Embeddings must keep 1024 dimensions (research R3);
otherwise re-embed after a migration.
