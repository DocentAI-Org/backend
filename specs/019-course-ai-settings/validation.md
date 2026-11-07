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
