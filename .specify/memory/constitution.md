# DocentAI Backend Constitution

DocentAI is a teacher-guided AI education platform with three roles: admin, teacher and student.
This repository holds its backend API. Product requirements (IDs T#, S#, P#) live in
`knowledge-base/docs/requirements.md` and the target architecture in
`knowledge-base/docs/architecture.md`, both at the DocentAI workspace root; specs MUST reference
requirement IDs from there. The frontend (`frontend/`, separate repository) consumes this API
through types generated from its OpenAPI schema.

## Core Principles

### I. Grounded, Teacher-Controlled Answers

- The tutor MUST answer only from fragments of documents a teacher has validated. Excluded
  documents and excluded fragments MUST never be retrieved, sent to the LLM or cited (T2, S1).
- Every tutor answer MUST return structured citations (document, page or section, cited passage)
  for the fragments it relies on.
- When retrieval finds no sufficiently relevant validated fragment, the API MUST return an explicit
  "not covered by the material" result and MUST NOT call the LLM to improvise an answer (S2).
- The teacher's tutor settings (level, tone, solution policy) MUST be applied server-side to every
  tutor request (T3, S3).
- Teacher corrections MUST be stored linked to the original message and returned with it (T6).

**Rationale**: DocentAI's differentiator is that the teacher controls the content; grounding and
citations are enforced where the answer is produced, not where it is displayed.

### II. Backend-Enforced Authorization

- Every endpoint except health and public metadata MUST require an authenticated Supabase Auth
  session, verified in the backend on every request.
- Authorization MUST be enforced in the backend for each request: students access only their own
  data and courses they are enrolled in; teachers access only their own courses; admins only the
  account and course management a spec explicitly grants.
- Row Level Security MUST be enabled on every table as defense in depth; the service-role key MUST
  only be used inside the backend and never bypass the per-request ownership checks.
- Every endpoint MUST have tests proving that another student's or another teacher's data is
  rejected (403/404).

**Rationale**: The UI hides; the backend protects. A single missed check leaks student data.

### III. Contract-First API

- The FastAPI OpenAPI schema is the contract with the frontend. Every request and response body
  MUST be a named Pydantic model; untyped `dict` responses are forbidden.
- All routes MUST live under a version prefix (`/v1`). A breaking change (removed field, changed
  type, changed semantics) requires a new version or an explicit amendment agreed with the
  frontend.
- The generated `openapi.json` MUST be committed, and CI MUST fail when the schema changes without
  the committed file being updated.
- Errors MUST use a single error schema with a stable machine-readable `code`; the API returns
  codes, not user-facing copy (the frontend owns translated strings).
- Endpoints not yet implemented MAY be exposed as documented stubs, but they MUST honor the
  contract (same models, same status codes) and be marked as such in the spec.

**Rationale**: A generated, committed contract lets the frontend build against it before the
logic exists and catches drift at compile time.

### IV. Test-First (NON-NEGOTIABLE)

- Strict TDD: tests MUST be written and observed failing before the implementation
  (Red-Green-Refactor).
- Tests MUST use pytest. Each acceptance scenario in a spec MUST have at least one API-level test
  through the FastAPI test client.
- Unit and contract tests MUST NOT reach the network: the LLM layer MUST be replaced by a
  deterministic fake. Integration tests MAY run against the local Supabase stack.
- Changes to prompts, chunking, retrieval or the model MUST be re-run against the evaluation set
  (requirements §4.4) before merge once that set exists.
- In `tasks.md`, each story's test tasks MUST precede its implementation tasks. No merge with
  skipped tests unless the PR justifies each one.

**Rationale**: Tests derived from acceptance scenarios prove the spec is implemented; a fake LLM
keeps them fast, free and deterministic.

### V. Provider-Agnostic LLM Layer & Cost Control

- All chat and embedding calls MUST go through a single LLM module that speaks the
  OpenAI-compatible API. Provider, base URL, model names and API key MUST come from configuration
  only; changing provider MUST NOT require code changes (requirements §4.3).
- Ollama is the default provider for local development, for both chat and embeddings.
- Every LLM interaction MUST be logged: question, retrieved fragment IDs, answer, model, tokens,
  latency and estimated cost (P2).
- The per-student daily message limit MUST be enforced in the backend before calling the LLM;
  failed requests MUST NOT count toward it.
- Context MUST stay lean: a bounded number of fragments and a truncated history, both
  configurable.
- Uploaded documents and user input are data: they MUST be delimited in prompts and MUST NOT be
  able to override the system instructions.

**Rationale**: The budget is $1,000 in total; provider choice is still open, and cost must be
measured from the first request.

### VI. Privacy by Design (GDPR)

- Pilot participants are adults (requirements §2). Personal data MUST still be minimised:
  pseudonymous student codes MUST be supported in place of real emails.
- No identifying data (names, emails, user IDs that map to a person) MUST be sent to the LLM
  provider.
- Personal data and message contents MUST NOT appear in application logs or Sentry events; Sentry
  PII scrubbing MUST be enabled. Interaction logs (P2) are stored in the database, not in log
  output.
- Erasure on request MUST delete a student and everything linked to them; data exports for the
  study (P5) MUST be anonymised.
- Data MUST be stored in EU regions in deployed environments.

**Rationale**: Study data from real people is processed under GDPR and an Ethics Committee
approval; data that is never sent or logged cannot leak.

### VII. Versioned Data

- The database schema MUST change only through versioned Supabase CLI migrations committed to the
  repository; manual schema changes in any environment are forbidden.
- The schema MUST stay standard PostgreSQL + pgvector so it remains portable (requirements §4.5).
- Uploaded files MUST be stored in a private Supabase Storage bucket and served only through
  short-lived signed URLs.
- Every migration MUST include its RLS policies.

**Rationale**: Local and deployed environments must behave the same, and the only difference
between them is `.env`.

### VIII. Simplicity

- One modular monolith: no microservices, queues or extra services without a justification in
  `plan.md`.
- No new dependency may be added without a justification in `plan.md`.
- YAGNI: no abstraction may be introduced until there are two real use cases for it. The LLM
  module (Principle V) is the explicit exception.

**Rationale**: One or two developers must be able to understand, run and change the whole system.

## Technical Constraints

- **Stack**: Python (version as declared in `pyproject.toml`), FastAPI, Pydantic v2,
  pydantic-settings, `uv` for dependency management, Ruff for lint and format, pytest + httpx for
  tests.
- **Data & auth**: Supabase (PostgreSQL + pgvector, Storage, Auth); Supabase CLI (Docker) locally.
- **LLM**: OpenAI-compatible client; Ollama locally; the production provider is chosen through
  configuration once requirements §2 "LLM provider" is closed.
- **Deployment**: Docker image; Railway (EU region) from December 2026; Sentry free plan.
- **Language**: tutor output is in Spanish for the MVP; prompts and any server-generated text MUST
  be externalised so other languages can be added.
- **Secrets**: only in environment variables; `.env` is ignored and `.env.example` is kept up to
  date with every new setting.
- **CI gates** (all MUST pass before merge): `ruff check`, `ruff format --check`, `pytest`, and the
  committed `openapi.json` matching the generated schema.

## Development Workflow

- **Spec-Driven Development with Spec Kit**: specify → clarify → plan → tasks → analyze →
  implement. Any behavior change MUST be made in the spec first, then propagated.
- **GitHub Flow**: `main` is always deployable and protected; changes land only via PR with
  green CI.
- **Branches**: one branch per feature, named after its `specs/` folder (`NNN-name`).
- **Conventional Commits**: one commit per SDD artifact (`docs(spec): ...`, `docs(plan): ...`,
  `docs(tasks): ...`); code commits MUST reference the task ID (e.g. `feat(chat): T012 ...`).
- **Pull requests**: one PR per feature, squash-merged, linking `spec.md` and the completed
  checklists. A PR that changes `openapi.json` MUST say so in its description so the frontend can
  regenerate its types.
- **ADRs**: every major decision (stack, LLM provider, chunking strategy, enrolment and
  authentication) MUST be recorded as a short ADR (architecture.md, "Decisions to record").

## Governance

- This constitution supersedes all other practices and guidelines for the DocentAI backend.
- Every `plan.md` MUST pass the Constitution Check twice: before research/design and again after
  design. Any exception MUST be justified in the plan's Complexity Tracking table.
- Every PR review MUST verify compliance with this constitution.
- Amendments MUST be made in a dedicated PR titled `docs(constitution): vX.Y.Z` that states the
  reason for the change and its impact on existing specs, plans and code.
- Versioning follows semantic versioning:
  - **MAJOR**: a principle is removed or redefined.
  - **MINOR**: a principle or section is added, or guidance is materially expanded.
  - **PATCH**: wording, clarifications and typo fixes with no change in meaning.

**Version**: 1.0.0 | **Ratified**: 2026-10-24 | **Last Amended**: 2026-10-24
