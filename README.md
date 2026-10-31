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
one LLM entry point (`app/llm/`) with three providers: Ollama locally, OpenAI or any
OpenAI-compatible API, and Anthropic. The provider and model are chosen per task through `.env`.

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

Edit `.env` only (specs/014). A default provider and model, and optionally one per task
(`TUTOR`, `FEEDBACK`, `REVIEW`, `QUESTIONS`), e.g. a cheap model for the chat and a stronger
one for exercise feedback, with embeddings kept on local Ollama:

```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-5-5
ANTHROPIC_API_KEY=…
LLM_FEEDBACK_MODEL=claude-sonnet-5-5
LLM_FEEDBACK_EFFORT=low
LLM_EMBEDDING_PROVIDER=ollama
```

Any OpenAI-compatible API (OpenAI, Mistral, vLLM…) is `openai` with its `OPENAI_BASE_URL`.
Anthropic takes no temperature (`LLM_FEEDBACK_TEMPERATURE` only applies to the others) and
has no embeddings. Costs in the interaction log use `LLM_PRICES` per model (current Claude
models are built in). Compare models with the evaluation: `LLM_FEEDBACK_PROVIDER=…
LLM_FEEDBACK_MODEL=… uv run pytest -m eval -s`.

Embeddings must stay 1024-dimensional (`EMBEDDING_DIMENSIONS`); a different size needs a
migration and re-processing the material. Re-tune `RETRIEVAL_MIN_SIMILARITY` and
`RETRIEVAL_MIN_SIMILARITY_EXERCISES` for a new embedding model.
