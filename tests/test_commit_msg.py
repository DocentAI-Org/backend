"""The commit-msg hook enforces the commit conventions in CONTRIBUTING.md."""

import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "commit-msg"


def run_hook(tmp_path: Path, message: str, rules: str = "commit") -> int:
    message_file = tmp_path / "COMMIT_EDITMSG"
    message_file.write_text(message, encoding="utf-8")
    return subprocess.run(
        [str(HOOK), str(message_file)],
        env={**os.environ, "COMMIT_RULES": rules},
        capture_output=True,
    ).returncode


@pytest.mark.parametrize(
    "message",
    [
        "feat(chat): T045 grounded tutor replies",
        "fix(material): T031-T037 handle empty pages",
        "feat(api)!: T050 rename topics endpoint",
        "docs(spec): 002 material topics",
        "docs(constitution): v1.1.0",
        "ci(github): run tests against Supabase",
        "test(access): T062 access matrix",
        "feat(chat): T045 respuestas con citas del material validado del curso\n",
        "fix(chat): T045 empty choices\n\nWhy it matters.\n\nCo-Authored-By: X <x@y.z>",
        "Merge branch 'main' into 001-api-v1-contract",
        "fixup! feat(chat): T045 grounded tutor replies",
        "# comment from git\nchore(deps): bump fastapi",
    ],
)
def test_valid_messages_pass(tmp_path: Path, message: str) -> None:
    assert run_hook(tmp_path, message) == 0


@pytest.mark.parametrize(
    "message",
    [
        "Add initial backend structure",
        "feat: T045 missing scope",
        "feat(chat): grounded tutor replies without task",
        "fix(chat): no task either",
        "Feat(chat): T045 wrong case",
        "feat(Chat): T045 uppercase scope",
        "feat(chat):T045 no space",
        "feat(chat): T045 trailing period.",
        "wip(chat): unknown type",
        "docs(spec): " + "x" * 61,
        "docs(spec): ñ" * 6,
        "feat(chat): T045 header\nbody without blank line",
        "feat(chat): T4500X not a task id",
    ],
)
def test_invalid_messages_fail(tmp_path: Path, message: str) -> None:
    assert run_hook(tmp_path, message) == 1


def test_header_length_counts_characters_not_bytes(tmp_path: Path) -> None:
    header = "docs(spec): " + "ñ" * 60  # 72 characters, 132 bytes

    assert run_hook(tmp_path, header) == 0


def test_pr_titles_do_not_need_a_task_id(tmp_path: Path) -> None:
    title = "feat(api): 001 API v1 contract for the MVP"

    assert run_hook(tmp_path, title, rules="pr-title") == 0
    assert run_hook(tmp_path, title) == 1
