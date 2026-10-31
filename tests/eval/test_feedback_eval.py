"""Classification of exercise mistakes against the local model (spec 006).

Not part of the normal suite: `uv run pytest -m eval -s`. Needs Supabase and Ollama
with the configured models. Each case is graded RUNS times in a rolled-back transaction;
the report gives verdict, type and topic accuracy and consistency across runs. Set
EVAL_REPORT to also write the report as Markdown.
"""

import json
import os
from collections import Counter
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.llm.client import get_llm
from tests.api.helpers import classroom
from tests.api.test_us6_topics import create_topic

CASES = json.loads((Path(__file__).parent / "feedback_cases.json").read_text())
RUNS = int(os.environ.get("EVAL_RUNS", "3"))

pytestmark = [pytest.mark.eval, pytest.mark.db]


@pytest.fixture
def llm():
    # The real model and the production thresholds, not the test ones.
    os.environ["RETRIEVAL_MIN_SIMILARITY"] = "0.55"
    os.environ["DAILY_MESSAGE_LIMIT"] = "1000"
    get_settings.cache_clear()
    yield get_llm()
    get_settings.cache_clear()


def assign_sections(client, teacher, course_id: str, document_id: str) -> None:
    """Confirmed topic assignments for each numbered section, as a teacher would."""
    fragments = client.get(
        f"/v1/teacher/courses/{course_id}/documents/{document_id}/fragments",
        headers=teacher.headers,
        params={"limit": 100},
    ).json()["items"]
    sections = {f["section"] for f in fragments}
    for name, number in CASES["topics"].items():
        topic = create_topic(client, teacher, course_id, name).json()
        for section in sorted(s for s in sections if number in s):
            response = client.post(
                f"/v1/teacher/courses/{course_id}/topic-assignments",
                headers=teacher.headers,
                json={
                    "topic_id": topic["id"],
                    "document_id": document_id,
                    "section": section,
                },
            )
            assert response.status_code == 201, response.text


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


def rate(values: list[bool]) -> str:
    return f"{sum(values)}/{len(values)} ({100 * sum(values) / len(values):.0f} %)"


def report(graded: list[dict], model: str) -> str:
    def flat(key):
        return [v for g in graded for v in g[key]]

    lines = [
        f"Model `{model}`, {RUNS} runs per case, {len(graded)} cases.",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Verdict | {rate(flat('verdicts'))} |",
        f"| Type (mistakes) | {rate(flat('types'))} |",
        f"| Topic (mistakes) | {rate(flat('topics'))} |",
        f"| Consistent cases | {rate([g['consistent'] for g in graded])} |",
        "",
        "| Case | Seen (verdict, type, topic) × runs |",
        "|---|---|",
    ]
    for g in graded:
        seen = "; ".join(
            f"{v}, {t or '—'}, {p or '—'} ×{n}" for (v, t, p), n in g["seen"].items()
        )
        lines.append(f"| `{g['id']}` | {seen} |")
    return "\n".join(lines)


def test_feedback_classification(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    assign_sections(client, teacher, room.course_id, room.document["id"])
    graded = []
    for case in CASES["cases"]:
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
    text = report(graded, get_settings().llm_chat_model)
    print("\n" + text)
    if path := os.environ.get("EVAL_REPORT"):
        Path(path).write_text(text + "\n")
