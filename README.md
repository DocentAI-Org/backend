# DocentAI Backend

Minimal base with FastAPI.

## Development

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
```

Run tests and lint:

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

Initial endpoints:

- `GET /health`
- `POST /chat`

The chat endpoint is a placeholder for connecting RAG, OpenAI, and Supabase later.
