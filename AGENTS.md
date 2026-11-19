# DocentAI backend

FastAPI service for DocentAI, a teacher-guided AI education platform with three roles: admin,
teacher and student. The frontend (`DocentAI-Org/frontend`) consumes this API through types
generated from `openapi.json`. Product requirements (IDs T#, S#, P#) live in
`DocentAI-Org/knowledge-base`, `docs/requirements.md`.

These are the rules for changing this repository, for people and coding agents alike.
`CONTRIBUTING.md` has the conventions for branches, commits and pull requests.

## Commands

```bash
uv sync                                           # dependencies
npx supabase start                                # local Postgres + pgvector, Auth, Storage
uv run uvicorn app.main:app --reload              # http://localhost:8000, docs at /docs
uv run python scripts/seed_dev.py                 # demo admin, teacher and student + tokens
uv run ruff check . && uv run ruff format --check .
uv run pyright                                    # types (basic mode)
uv run python scripts/export_openapi.py --check   # without --check: regenerate openapi.json
uv run pytest --cov                               # needs `npx supabase db start`; fails under 95 %
uv run pytest -m "not db"                         # unit tests only, no database
```

CI runs all of them except the last; all must pass before merge. GitHub also runs CodeQL on every
pull request, and Dependabot proposes dependency and action updates. A rule silenced in code
(`# noqa`, `# type: ignore`, `cast`) says why next to it.

## Rules

Code comments cite them by number, e.g. "AGENTS.md II".

### I. Grounded, teacher-controlled answers

- The tutor answers only from fragments of documents a teacher has validated. Excluded documents
  and fragments are never retrieved, sent to the LLM or cited (T2, S1).
- Every tutor answer returns structured citations (document, page or section, cited passage) for
  the fragments it relies on.
- When retrieval finds no sufficiently relevant validated fragment, the API returns an explicit
  "not covered by the material" result and does not call the LLM to improvise (S2).
- The teacher's tutor settings (level, tone, solution policy) are applied server-side to every
  tutor request (T3, S3).
- Teacher corrections are stored linked to the original message and returned with it (T6).

### II. Backend-enforced authorization

- Every endpoint except health and public metadata requires a Supabase Auth session, verified
  here on every request.
- Authorization is enforced per request: students reach only their own data and the courses they
  are enrolled in; teachers only their own courses; admins only the account and course management
  explicitly granted to them.
- Row Level Security is enabled on every table as defence in depth. The service-role key is used
  only inside the backend and never bypasses the per-request ownership checks.
- Every endpoint has tests proving that another student's or teacher's data is rejected (403/404).

### III. Contract-first API

- The OpenAPI schema is the contract with the frontend. Every request and response body is a
  named Pydantic model; untyped `dict` responses are forbidden.
- Routes live under `/v1`. A breaking change (removed field, changed type or meaning) needs a new
  version or an explicit change agreed with the frontend.
- `openapi.json` is committed, and CI fails when the schema changes without it.
- Errors use one error schema with a stable machine-readable `code`; the API returns codes, not
  user-facing copy (the frontend owns translated strings).

### IV. Test-first

- Tests are written and seen failing before the implementation.
- pytest; every acceptance scenario has at least one API-level test through the test client.
- Unit and contract tests never reach the network: the LLM layer is replaced by the deterministic
  fake in `tests/fakes.py`. Integration tests may use the local Supabase stack.
- No merge with skipped tests unless the pull request justifies each one.

### V. One provider-agnostic LLM layer, with costs measured

- Every chat and embedding call goes through `app/llm/`. Provider, base URL, model and key come
  from configuration only; changing provider needs no code change.
- Ollama is the default for local development, for chat and embeddings.
- Every LLM interaction is logged: question, retrieved fragment IDs, answer, model, tokens,
  latency and estimated cost (P2).
- The per-student message limit is enforced before calling the LLM; failed requests do not count.
- Context stays lean: a bounded number of fragments and a truncated history, both configurable.
- Uploaded documents and user input are data: they are delimited in prompts and cannot override
  the system instructions.
- Changes to prompts, chunking, retrieval or the default model are measured on real models before
  merge, and the pull request reports the result.

### VI. Privacy by design (GDPR)

- Personal data is minimised: pseudonymous student codes are supported in place of emails.
- No identifying data (names, emails, user IDs that map to a person) is sent to an LLM provider.
- Personal data and message contents never appear in application logs or Sentry events; Sentry
  PII scrubbing is on. Interaction logs (P2) are stored in the database, not in log output.
- Erasure on request deletes a student and everything linked to them; study exports (P5) are
  anonymised.
- Deployed environments store data in EU regions.

### VII. Versioned data

- The schema changes only through Supabase CLI migrations in `supabase/migrations/`, each with
  its RLS policies. Manual schema changes are forbidden in every environment.
- The schema stays standard PostgreSQL + pgvector.
- Uploaded files go to a private Storage bucket and are served only through short-lived signed
  URLs.

### VIII. Simplicity

- One modular monolith: no microservices, queues or extra services without a justification in the
  pull request. The same for every new dependency.
- No abstraction before two real uses for it; the LLM layer is the exception.

## Technical constraints

- Python (version in `pyproject.toml`), FastAPI, Pydantic v2, pydantic-settings, `uv`, Ruff,
  pytest + httpx; Supabase (PostgreSQL + pgvector, Storage, Auth), its CLI locally.
- Tutor output is in Spanish for now; prompts and server-generated text live outside code
  (`app/prompts/`), so other languages can be added.
- Secrets only in environment variables. `.env` is ignored; `.env.example` documents every
  setting.
- Deployment: Docker image on Railway (EU region), Sentry.

## Feature numbers

Comments and docstrings that cite `spec NNN` or `specs/NNN` name the feature that introduced the
code: its branch is `NNN-name` and its pull request explains it.

## For tools outside this repository

A development or evaluation tool may rely on the commands above and on these files, and on
nothing else. Changing them is a change to this repository, made in a pull request that says so:

- `openapi.json`, the API contract.
- `.env.example`, the settings and their meaning.
- The test fixtures in `tests/conftest.py` (`client`, `db`, `llm`, `make_user`, `teacher`,
  `student`) and the helpers they are used with: `tests/api/helpers.py`, `create_course` in
  `tests/api/test_us2_courses.py`, `upload` in `tests/api/test_us3_material.py`, `create_topic` in
  `tests/api/test_us6_topics.py`, `build_docx` in `tests/builders.py`, and `tests/fixtures/`.
- `app.core.config` (`get_settings`, `Task`), `app.llm.client` (`get_llm`, `LLMClient`,
  `ChatResult`, `OpenAICompatProvider`), `app.models.Fragment` and
  `app.services.retrieval.retrieve`, to run the app's real models outside the test suite.
