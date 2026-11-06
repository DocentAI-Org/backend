"""Classification of exercise mistakes against the local model (specs/009, 017).

Not part of the normal suite: `uv run pytest -m eval -s`. Needs Supabase and Ollama
with the configured models. Each case of each subject is graded RUNS times in a
rolled-back transaction; the report gives verdict, type and topic accuracy and
consistency across runs, by subject. Set EVAL_REPORT to also write it as Markdown.
"""

import os
from collections import Counter
from pathlib import Path

import pytest

from tests.eval.report import (
    available,
    model_label,
    rate,
    share,
    table,
    write_results,
)
from tests.eval.subjects import enrolled_student, open_room, subjects

RUNS = int(os.environ.get("EVAL_RUNS", "3"))

pytestmark = [pytest.mark.eval, pytest.mark.db]


def grade(results: list[dict], case: dict) -> dict:
    mistake = case["verdicts"] != ["correct"]
    verdicts = [r["verdict"] in case["verdicts"] for r in results]
    types = [r["error_type"] in case["types"] for r in results] if mistake else []
    topics = [r["topic_name"] in case["topics"] for r in results] if mistake else []
    labels = Counter((r["verdict"], r["error_type"], r["topic_name"]) for r in results)
    return {
        "id": case["id"],
        "verdicts": verdicts,
        "types": types,
        "topics": topics,
        "consistent": len(labels) == 1,
        "seen": labels,
    }


def summary(graded: list[dict]) -> dict:
    def flat(key):
        return [v for g in graded for v in g[key]]

    return {
        "verdict": share(flat("verdicts")),
        "type": share(flat("types")),
        "topic": share(flat("topics")),
        "consistent": share([g["consistent"] for g in graded]),
        "counts": {
            "verdict": rate(flat("verdicts")),
            "type": rate(flat("types")),
            "topic": rate(flat("topics")),
            "consistent": rate([g["consistent"] for g in graded]),
        },
    }


def report(by_subject: dict[str, list[dict]], model: str, latency: dict) -> str:
    every = [g for graded in by_subject.values() for g in graded]
    rows = []
    for slug, graded in [*by_subject.items(), ("**all**", every)]:
        counts = summary(graded)["counts"]
        rows.append(
            [
                slug,
                counts["verdict"],
                counts["type"],
                counts["topic"],
                counts["consistent"],
            ]
        )
    lines = [
        f"Model `{model}`, {RUNS} runs per case, {len(every)} cases, "
        f"median {latency['median_ms']} ms per call.",
        "",
        *table(
            ["Subject", "Verdict", "Type (mistakes)", "Topic (mistakes)", "Consistent"],
            rows,
        ),
        "",
        *table(
            ["Case", "Seen (verdict, type, topic) × runs"],
            [
                [
                    f"`{slug}/{g['id']}`",
                    "; ".join(
                        f"{v}, {t or '—'}, {p or '—'} ×{n}"
                        for (v, t, p), n in g["seen"].items()
                    ),
                ]
                for slug, graded in by_subject.items()
                for g in graded
            ],
        ),
    ]
    return "\n".join(lines)


def test_feedback_classification(client, db, llm, make_user, teacher) -> None:
    # The study's default repeated-mistake count (spec 015); more runs would trigger S8.
    assert RUNS <= 3, "EVAL_RUNS would trigger the adaptation note"
    by_subject: dict[str, list[dict]] = {}
    for subject, content in available(subjects()):
        room = open_room(client, db, teacher, subject, content)
        graded = []
        for case in subject.data["feedback"]:
            # A student of their own for each case: with RUNS < 4 they never reach the
            # repeated mistakes that switch on the adaptation note (spec 013).
            student = enrolled_student(client, make_user, room)
            results = []
            for _ in range(RUNS):
                response = client.post(
                    f"/v1/student/courses/{room.course_id}/submissions",
                    headers=student.headers,
                    json={
                        "problem_statement": case["statement"],
                        "worked_answer": case["answer"],
                    },
                )
                assert response.status_code == 201, response.text
                results.append(response.json())
            graded.append(grade(results, case))
        by_subject[subject.slug] = graded

    model = model_label("feedback")
    latency = llm.latency("feedback")
    text = report(by_subject, model, latency)
    print("\n" + text)
    if path := os.environ.get("EVAL_REPORT"):
        Path(path).write_text(text + "\n")
    every = [g for graded in by_subject.values() for g in graded]
    write_results(
        "feedback",
        model,
        {
            "runs": RUNS,
            "latency": latency,
            "overall": summary(every),
            "by_subject": {slug: summary(g) for slug, g in by_subject.items()},
            "cases": {
                slug: {
                    g["id"]: [list(k) + [n] for k, n in g["seen"].items()]
                    for g in graded
                }
                for slug, graded in by_subject.items()
            },
        },
    )
