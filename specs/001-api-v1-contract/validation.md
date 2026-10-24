# Validation: DocentAI API v1

**Feature**: [spec.md](spec.md) · **Date**: 2026-10-24 · **Environment**: macOS (Apple Silicon),
Docker 29.9, Supabase CLI 2.122.0 (Postgres 17), Ollama with `qwen2.5:7b` and `bge-m3`.

## Automated suite

`uv run pytest` → **112 passed** (unit, API against local Supabase Postgres, contract).
`ruff check`, `ruff format --check` and `export_openapi.py --check` pass. The contract has 47
paths and 61 operations.

| Success criterion | Result | Evidence |
|---|---|---|
| SC-001 types for every M field | ✅ | `openapi.json`; every route under `/v1`, every success response typed (`tests/contract`) |
| SC-002 cross-user/role rejection | ✅ | `tests/api/test_access_matrix.py`: every operation × no token (401), wrong role (403), other teacher/student on a course route (404) |
| SC-003 citations / `no_source` | ✅ | `test_us4_chat.py` with the fake model; also with real models below |
| SC-004 logs complete, no PII to the model | ✅ | `test_us4_logging.py`, `test_prompt_never_contains_identifying_data` |
| SC-005 fresh clone → cited answer < 15 min | ⚠️ partly | Steps work as written. The first `supabase start` pulled ~2.6 GB of images and took longer than 15 min on this network; with images cached, start-up to cited answer took ~2 min |
| SC-006 switch provider by config only | ⚠️ partly | Fake and Ollama run through the same client and test suite; no hosted provider key was available to try one |
| SC-007 allowance under 10 concurrent requests | ✅ | `test_concurrent_reservations_never_exceed_the_limit` (real commits, 10 threads, limit 5 → 5) |
| SC-008 reply < 10 s p95 locally | ✅ warm / ⚠️ cold | Warm model 2.0–2.7 s; first call after loading the model 8.7–10.2 s |

## End-to-end run against real services

Real Supabase Auth (ES256 tokens verified through JWKS), Storage and Postgres, real Ollama. Script
in the quickstart order:

1. Teacher creates course, uploads `tests/fixtures/ecuaciones.md` → `ready`, 4 fragments, 1.1 s;
   signed URL downloads the file (200). Validate, student joins and acknowledges disclosure.
2. "¿Cómo despejo la x en 2x + 3 = 7?" → `hint` 1, cites § 3.1.
3. "No lo entiendo, ¿me das otra pista?" → `hint` 2, cites § 3.1 and § 3.2 (follow-up after a
   hint searches with the previous question).
4. "¿Qué pasa con un signo menos delante de un paréntesis?" → `hint` 3, cites § 3.3.
5. "¿Quién ganó el mundial de 2010?" → `no_source`, 0.1 s, **no model call**.
6. Allowance and interaction logs (`model`, tokens, latency, cost 0, HMAC student ref) correct.
7. Admin creates a teacher and two pseudonymous students (`EST-XXXXX`); a pseudonymous student
   signs in with code + password and `/v1/me` shows `is_pseudonymous: true`, `email: null`.
   Duplicate teacher email → `409 email_taken`.

### Finding fixed during validation

The first run used `RETRIEVAL_MIN_SIMILARITY=0.45` and always searched with the previous question
joined to the new one. The off-topic question then retrieved fragments and reached the model
(which correctly answered `no_source`, so grounding held, but the call cost time and tokens).
Measured bge-m3 similarities on the sample: covered questions 0.62–0.76, off-topic 0.22–0.48.
Fix: default threshold 0.55, and the previous question is used only for follow-ups right after a
hint (research R5, R6; test `test_new_question_after_an_answer_is_judged_on_its_own`).

## Known gaps (not blocking this feature)

- Exercise feedback is a stub (FR-100, R17) until the error taxonomy exists.
- Topic suggestions (FR-073) are not generated yet; manual assignment works.
- `RETRIEVAL_MIN_SIMILARITY` was tuned on one sample document; re-tune with the evaluation set
  (requirements §4.4) before the pilot.
- In guided mode, the model sometimes answers a conceptual question as a `hint` (step 4). The
  policy is respected; refine the prompt with the evaluation set.
- Sentry and deployment (Railway, Supabase Pro) are out of scope for this feature.
- The CI workflow has not run on GitHub yet (branch not pushed).
