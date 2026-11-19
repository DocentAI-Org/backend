# Contributing

The rules for the code are in `AGENTS.md`; these are the conventions for branches, commits and
pull requests. Git hooks check them locally and the `PR conventions` workflow checks them on every
pull request.
The hooks in `.githooks/` are mirrored in the frontend repository: change both together.

## Set up the hooks (once per clone)

```bash
git config core.hooksPath .githooks
```

- `pre-commit`: refuses commits on `main`, runs Ruff on staged Python files and, when `app/`
  changes, checks that `openapi.json` is up to date.
- `commit-msg`: checks the message format below.

## Branches

- A feature: its number and name, e.g. `001-api-v1-contract`.
- Anything else: `<type>/<name>`, e.g. `ci/commit-conventions`, `fix/upload-names`.

## Commit messages

```text
<type>(<scope>): <description>

<optional body: why, not what>
```

- Types: `feat`, `fix`, `docs`, `test`, `build`, `ci`, `chore`, `refactor`, `perf`, `style`,
  `revert`. The scope is required and lowercase.
- Header of at most 72 characters, no trailing period.
- `feat` and `fix` reference their task IDs: `feat(chat): T045 grounded replies`.
- Changes to `AGENTS.md` rules: `docs(agents): …`, with the reason in the body.

## Pull requests

- One PR per feature, squash-merged. The PR title becomes the commit, so it follows the same
  format (a task ID is not required in the title).
- A PR that changes `openapi.json` says so in "API contract", so the frontend can regenerate its
  types.
- The description follows the template: summary, type, feature, what changes, API contract,
  database, how to verify, dependencies and merge order, risks and rollback, checks, and known
  gaps. CI fails if "Summary" or "How to verify" is empty. Write "None" or "n/a" in a section that
  does not apply.
- "How to verify" is written for a reviewer who has not followed the work: setup (database,
  seed, Ollama models), the commands to run, and the requests to try with the expected responses.

`git commit --no-verify` skips the local hooks; CI still checks every commit of the PR.
