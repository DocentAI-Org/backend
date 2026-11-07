# Tasks: AI Settings per Course

**Spec**: [spec.md](spec.md)

Delivered in three PRs against `main`, one after the other (never stacked).

## PR 1 — Settings, limits and models (US1, US2, US6)

- [x] T001 Tests first: study defaults and course overrides, validation, roles; per-course limit
  with each period, no limit, global ceiling, counted tasks, release on failure; routing per
  course and task (`tests/api/test_ai_settings.py`, `tests/api/test_course_allowance.py`)
- [x] T002 Migration, models, schemas; `app/services/ai_settings.py` (course, study, server)
- [x] T003 [US1] Allowance per course and period, ceiling, counted tasks; student route
- [x] T004 [US2] `chat_json` takes the course's route; temperature, effort, max tokens and
  retrieval read from the course
- [x] T005 [US2] Model catalogue (Ollama tags, server keys) with cache and timeouts
- [x] T006 Contract note and `openapi.json`

## PR 2 — Credentials (US3)

- [x] T007 Tests first: add, check, encrypt, last4 only, delete erases, `allow_teacher_keys`,
  roles, a removed credential or model resets the course group (`tests/api/test_llm_credentials.py`)
- [x] T008 `cryptography` as a direct dependency; `LLM_CREDENTIALS_KEY`; `llm_credentials`
  service and routes; providers built per credential; catalogue lists credential models
- [x] T009 Keys absent from logs, errors and the study export (test)
- [x] T010 Requirements §4.1/§4.2 update in the knowledge base; contract note and `openapi.json`

## PR 3 — Instructions, test and usage (US4, US5)

- [x] T011 Tests first: instruction block position and length, retrieval options, test message
  (not logged, no allowance, rate limit), usage figures (`tests/api/test_ai_tools.py`)
- [x] T012 Teacher instruction block in the four prompts
- [x] T013 `ai-test` and `ai-usage` routes
- [x] T014 Evaluation unchanged with no overrides (SC-002: same prompts, tested; not re-run);
  validation on the real stack
