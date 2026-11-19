<!-- Title: <type>(<scope>): <description>, at most 72 characters. It becomes the squash commit. -->
<!-- CI checks that "Summary" and "How to verify" have content. Write "None" or "n/a" rather than
     leaving another section empty; comments like this one can stay, they are ignored. -->

## Summary

<!-- What changes and why, in a few lines, for someone who has not followed the work. -->

## Type of change

- [ ] Feature (`NNN-name`)
- [ ] Fix
- [ ] Refactor (no behavior change)
- [ ] Docs, CI or tooling

## What changes

<!-- The main changes by area, so reviewers know where to look: endpoints (`app/api`), services,
     models and schemas, RAG and LLM prompts, tests, configuration. -->

## API contract

<!-- Does `openapi.json` change? New, changed or removed endpoints, fields and error codes; whether
     it is breaking; the frontend PR that follows (types regenerated from the new contract).
     Otherwise "No change". -->

## Database

<!-- New migrations in `supabase/migrations/`, RLS policies, seed changes, and whether existing
     data is rewritten. Otherwise "No change". -->

## How to verify

<!-- Steps a reviewer can follow without asking:
     - Setup: branch, `uv sync`, `npx supabase start` (and `db reset` if there are migrations),
       `scripts/seed_dev.py`, the Ollama models if the LLM is involved, new env vars.
     - Automated: the commands to run, e.g. `uv run pytest tests/api/test_xxx.py`.
     - Manual: requests to try in `http://localhost:8000/docs` or with curl (token from the
       seed script), and the expected responses. -->

## Dependencies and merge order

<!-- Related PRs (e.g. DocentAI-Org/frontend#N) and the order to merge them. Otherwise "None". -->

## Risks and rollback

<!-- Breaking changes, migrations that cannot be undone, data or privacy impact, and how to
     revert. Otherwise "None". -->

## Checks

- [ ] Follows the rules in `AGENTS.md`
- [ ] Tests written first and seen failing; none skipped without a reason below
- [ ] `openapi.json` exported and checked; the frontend must regenerate its types if it changed
- [ ] Migrations apply on a clean database (`supabase db reset`) and RLS covers new tables
- [ ] No personal data in logs, prompts or fixtures
- [ ] New settings documented in `.env.example`

## Known gaps and follow-ups

<!-- What is left out on purpose, open decisions and follow-up tasks. Otherwise "None". -->
