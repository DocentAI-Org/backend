"""Compares Ollama models on the evaluation (specs/017 US3).

Runs the feedback, tutor and quiz-draft evaluations once per model, with that model for
every task, saves each model's results as JSON and writes a Markdown comparison:

    uv run python scripts/eval_models.py qwen2.5:7b qwen3:8b@none gemma4:e4b@none

`model@effort` sets LLM_EFFORT for that model (`none` turns thinking off). Needs
Supabase, Ollama with the models pulled, and the corpus (scripts/eval_corpus.py).
Results go to `--out` (default `tests/eval/results/`, git-ignored); `--report` only
rebuilds the comparison from them.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ("feedback", "tutor", "questions")
FILES = {
    "feedback": "tests/eval/test_feedback_eval.py",
    "tutor": "tests/eval/test_tutor_eval.py",
    "questions": "tests/eval/test_questions_eval.py",
}


def folder(spec: str) -> str:
    return spec.replace(":", "_").replace("/", "_").replace("@", "_at_")


def run(spec: str, tasks: list[str], out: Path, runs: int) -> int:
    model, _, effort = spec.partition("@")
    env = {
        key: value
        for key, value in os.environ.items()
        if not (
            key.startswith("LLM_") and key.endswith(("_PROVIDER", "_MODEL", "_EFFORT"))
        )
    }
    env |= {
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": model,
        "LLM_CHAT_MODEL": model,
        "EVAL_OUT": str(out / folder(spec)),
        "EVAL_RUNS": str(runs),
    }
    # The .env file must not give a task another model or effort.
    for task in ("TUTOR", "FEEDBACK", "REVIEW", "QUESTIONS"):
        env[f"LLM_{task}_MODEL"] = model
        env[f"LLM_{task}_PROVIDER"] = "ollama"
    if effort:
        env["LLM_EFFORT"] = effort
        for task in ("TUTOR", "FEEDBACK", "REVIEW", "QUESTIONS"):
            env[f"LLM_{task}_EFFORT"] = effort
    print(f"== {spec}", flush=True)
    command = [
        "uv",
        "run",
        "pytest",
        "-m",
        "eval",
        "-s",
        "-q",
        *(FILES[t] for t in tasks),
    ]
    return subprocess.run(command, cwd=ROOT, env=env).returncode


def load(out: Path, spec: str) -> dict[str, dict]:
    path = out / folder(spec)
    return {
        task: json.loads((path / f"{task}.json").read_text())
        for task in TASKS
        if (path / f"{task}.json").exists()
    }


def pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.0f}"


def comparison(out: Path, specs: list[str]) -> str:
    results = {spec: load(out, spec) for spec in specs}
    header = [
        "Model",
        "Verdict",
        "Type",
        "Topic",
        "Consistent",
        "Tutor kind",
        "Citation",
        "Usable drafts",
        "Key confirmed",
        "Median s (feedback / tutor / questions)",
        "Errors",
    ]
    rows = []
    for spec, r in results.items():
        fb = r.get("feedback", {}).get("overall", {})
        tu = r.get("tutor", {}).get("overall", {})
        qu = r.get("questions", {}).get("overall", {})
        latency = " / ".join(
            f"{r[t]['latency']['median_ms'] / 1000:.1f}"
            if t in r and r[t]["latency"]["median_ms"]
            else "—"
            for t in TASKS
        )
        rows.append(
            [
                f"`{spec}`",
                pct(fb.get("verdict")),
                pct(fb.get("type")),
                pct(fb.get("topic")),
                pct(fb.get("consistent")),
                pct(tu.get("kind")),
                pct(tu.get("citation")),
                pct(qu.get("usable")),
                pct(qu.get("key_confirmed")),
                latency,
                str(sum(r[t]["latency"].get("errors", 0) for t in r)),
            ]
        )
    lines = ["Percentages over all subjects.", "", *markdown(header, rows)]

    subjects = sorted(
        {
            s
            for r in results.values()
            for t in r.values()
            for s in t.get("by_subject", {})
        }
    )
    for title, task, metric in (
        ("Feedback verdict", "feedback", "verdict"),
        ("Feedback error type", "feedback", "type"),
        ("Feedback topic", "feedback", "topic"),
        ("Tutor kind", "tutor", "kind"),
        ("Quiz keys confirmed by the judge", "questions", "key_confirmed"),
    ):
        rows = [
            [f"`{spec}`"]
            + [
                pct(r.get(task, {}).get("by_subject", {}).get(s, {}).get(metric))
                for s in subjects
            ]
            for spec, r in results.items()
        ]
        lines += [
            "",
            f"### {title} by subject",
            "",
            *markdown(["Model", *subjects], rows),
        ]
    return "\n".join(lines)


def markdown(header: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "models", nargs="+", help="Ollama models, optionally model@effort"
    )
    parser.add_argument("--tasks", default=",".join(TASKS))
    parser.add_argument("--runs", type=int, default=2, help="feedback runs per case")
    parser.add_argument("--out", type=Path, default=ROOT / "tests/eval/results")
    parser.add_argument("--report", action="store_true", help="only rebuild the table")
    args = parser.parse_args()
    tasks = [t for t in args.tasks.split(",") if t]
    failed = []
    if not args.report:
        for spec in args.models:
            if run(spec, tasks, args.out, args.runs) != 0:
                failed.append(spec)
    text = comparison(args.out, args.models)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "comparison.md").write_text(text + "\n")
    print("\n" + text)
    if failed:
        print(f"\nFailed runs: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
