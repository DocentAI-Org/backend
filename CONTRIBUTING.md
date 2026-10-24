# Contributing

The rules come from the constitution (`.specify/memory/constitution.md`, Development Workflow).
Git hooks check them locally and the `PR conventions` workflow checks them on every pull request.
The hooks in `.githooks/` are mirrored in the frontend repository: change both together.

## Set up the hooks (once per clone)

```bash
git config core.hooksPath .githooks
```

- `pre-commit`: refuses commits on `main`, runs Ruff on staged Python files and, when `app/`
  changes, checks that `openapi.json` is up to date.
- `commit-msg`: checks the message format below.

## Branches

- A Spec Kit feature: the name of its `specs/` folder, e.g. `001-api-v1-contract`.
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
- One commit per Spec Kit artifact: `docs(spec): …`, `docs(plan): …`, `docs(tasks): …`.
  Amendments to the constitution: `docs(constitution): vX.Y.Z`.

## Pull requests

- One PR per feature, squash-merged. The PR title becomes the commit, so it follows the same
  format (a task ID is not required in the title).
- Feature PRs link `specs/NNN-name/spec.md` in the description; the template has the place.
- A PR that changes `openapi.json` says so, so the frontend can regenerate its types.

`git commit --no-verify` skips the local hooks; CI still checks every commit of the PR.
