# DocentAI Backend

Minimal base with FastAPI.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Initial endpoints:

- `GET /health`
- `POST /chat`

The chat endpoint is a placeholder for connecting RAG, OpenAI, and Supabase later.
