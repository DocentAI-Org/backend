<!-- Title: <type>(<scope>): <description>, at most 72 characters. It becomes the squash commit. -->

## Summary

<!-- What changes and why, in a few lines. -->

## Spec and tasks

<!-- Feature PRs (branch NNN-name) must link their spec; CI checks it. -->

- Spec: `specs/NNN-name/spec.md`
- Tasks: T###–T###
- Checklists: `specs/NNN-name/checklists/`

## Checks

- [ ] Constitution Check passed in `plan.md` (before and after design)
- [ ] Tests written first and seen failing; none skipped without a reason below
- [ ] `openapi.json` changed: the frontend must regenerate its types
- [ ] No personal data in logs, prompts or fixtures
- [ ] New settings documented in `.env.example`
