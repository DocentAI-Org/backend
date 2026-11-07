# Validation: AI Settings per Course (PR 1)

**Date**: 2026-11-07 · **Stack**: local Supabase (CLI, real Auth), API on port 8077,
`seed_dev.py` users, Ollama on the M2 Pro with 11 models (server model `qwen2.5:3b` in `.env`).

The API tests (`test_ai_settings.py`, `test_course_allowance.py`, the concurrency test in
`test_us4_allowance.py`; full suite 414 passed) use a fake model and catalogue. This run checks the
real catalogue, routing and limits.

| Check | Result |
|---|---|
| `GET /admin/ai-models` | Ollama reachable, 11 chat models; `bge-m3` (embeddings) left out |
| Server values | tutor `qwen2.5:3b` (from `.env`), ceiling 30 |
| A model Ollama does not have | 422 `model_unavailable` |
| Course: tutor `qwen2.5:7b` (temperature 0.1, 600 tokens), 2 messages a week, only the tutor counts | saved; origin `course` |
| Two tutor messages | 201 in 7.3 s and 9.8 s; the interaction log keeps `qwen2.5:7b` for both |
| Third message | 429 `course_limit_reached`, `period: week`, resets Monday 2026-11-09 00:00 Europe/Madrid |
| `allowance` (tutor) / `?task=feedback` | course 2/2 / the daily ceiling, 2 of 30 used |

Not checked on the real stack: OpenAI and Anthropic (no keys yet); an unreachable Ollama (covered
by the fake catalogue).

# Validation: Credentials (PR 2)

**Date**: 2026-11-08 · **Stack**: as above, with a development `LLM_CREDENTIALS_KEY` in `.env`.

The API tests (`test_llm_credentials.py`, 16 tests; full suite 431 passed) use a fake catalogue.
With no OpenAI or Anthropic account yet, this run uses the real OpenAI API with a made-up key,
and the local Ollama reached through a stored OpenAI-compatible key, which exercises the same
path a commercial key would.

| Check | Result |
|---|---|
| A made-up key against the real OpenAI API | 422 `key_rejected`; the key is not in the response |
| An OpenAI-compatible key for `http://localhost:11434/v1` | 201, `…1234`; stored as a Fernet token, the key not in the row |
| `GET /llm-credentials/{id}/models` | reachable, 12 models (the key's catalogue is not filtered: the admin chooses) |
| Only `qwen2.5:3b` offered | the course lists it under the key, scope `study`, besides the server's Ollama |
| The tutor through the key | 201 in 4.6 s; the log keeps `qwen2.5:3b` |
| Deleting the key | the row is gone; the course's tutor goes back to the inherited model with a `credential_removed` notice |
| Both keys in the API log | absent |
