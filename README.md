# DocentAI Backend

FastAPI service for DocentAI: a teacher-guided AI tutor that answers only from material the
teacher has validated, and cites it.

- **Contract**: [`openapi.json`](openapi.json) (committed; the frontend generates its types from
  it). Interactive docs at `http://localhost:8000/docs`.
- **Spec-driven**: specs, plans and tasks live in [`specs/`](specs/); principles in
  [`.specify/memory/constitution.md`](.specify/memory/constitution.md). Current feature:
  [`specs/001-api-v1-contract`](specs/001-api-v1-contract/spec.md).

## Stack

Python + FastAPI, SQLAlchemy over Supabase Postgres + pgvector, Supabase Auth and Storage, and
one OpenAI-compatible LLM client: Ollama locally, any compatible provider (open or closed models)
in production, chosen only through `.env`.

## Local development

Prerequisites: Docker, Node.js (for `npx supabase`), `uv`, and Ollama with the default models:

```bash
ollama pull qwen2.5:7b
ollama pull bge-m3
```

Then:

```bash
uv sync
npx supabase start                 # Postgres + pgvector, Auth, Storage; applies migrations
cp .env.example .env               # fill SUPABASE_SERVICE_ROLE_KEY and SUPABASE_JWT_SECRET
npx supabase status -o env         # ...from SERVICE_ROLE_KEY and JWT_SECRET here
uv run uvicorn app.main:app --reload
uv run python scripts/seed_dev.py  # demo admin, teacher and student + access tokens
```

The full walkthrough is in
[`specs/001-api-v1-contract/quickstart.md`](specs/001-api-v1-contract/quickstart.md).

## Checks (same as CI)

```bash
uv run ruff check . && uv run ruff format --check .
uv run python scripts/export_openapi.py --check   # regenerate without --check after API changes
uv run pytest                                     # needs `npx supabase db start`
uv run pytest -m "not db"                         # unit tests only, no database
```

Tests never call a model provider: they use a deterministic fake (`tests/fakes.py`).

## Layout

| Path | What |
|---|---|
| `app/routers/{admin,teacher,student}` | role-scoped `/v1` routes |
| `app/services/` | business logic (courses, material, retrieval, tutor, allowance…) |
| `app/llm/` | the only place that talks to a model provider |
| `app/prompts/es/` | tutor prompts and fixed texts, outside code |
| `supabase/migrations/` | the database schema, RLS and storage bucket |
| `scripts/` | OpenAPI export/check, local seed |

## Changing the model provider

Edit `.env` only, e.g. for Mistral:

```env
LLM_BASE_URL=https://api.mistral.ai/v1
LLM_API_KEY=…
LLM_CHAT_MODEL=mistral-small-latest
LLM_EMBEDDING_MODEL=mistral-embed
LLM_PRICE_INPUT_PER_MTOK=0.1
LLM_PRICE_OUTPUT_PER_MTOK=0.3
```

Embeddings must stay 1024-dimensional (`EMBEDDING_DIMENSIONS`); a different size needs a
migration and re-processing the material. Re-tune `RETRIEVAL_MIN_SIMILARITY` and
`RETRIEVAL_MIN_SIMILARITY_EXERCISES` for a new embedding model.
