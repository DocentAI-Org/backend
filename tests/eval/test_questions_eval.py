"""AI quiz drafts on each subject (specs/017 US2.4).

`uv run pytest -m eval -s tests/eval/test_questions_eval.py`. For each topic listed in
`questions`, COUNT drafts are requested. A draft counts as usable when it survives
`validate_drafts`; its key counts as confirmed when a judge model (EVAL_JUDGE_MODEL,
Ollama), shown the cited passages and the options but not the key, picks the same
option. The judge is small too: its disagreements are listed for a person to check.
"""

import os

import pytest
from openai import OpenAI

from app.core.config import get_settings
from app.llm.client import OpenAICompatProvider
from tests.eval.report import (
    available,
    model_label,
    rate,
    share,
    table,
    write_results,
)
from tests.eval.subjects import open_room, subjects

COUNT = int(os.environ.get("EVAL_QUESTIONS", "3"))
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "qwen2.5:7b")
LETTERS = "ABCD"

JUDGE_PROMPT = (
    "Eres un profesor que comprueba preguntas de opción múltiple. Lee el material y "
    "responde a la pregunta eligiendo la única opción correcta según el material. "
    'Responde solo con JSON: {"razonamiento": "<breve>", "opcion": "A"|"B"|"C"|"D"}.'
)

pytestmark = [pytest.mark.eval, pytest.mark.db]


def judge(provider: OpenAICompatProvider, question: dict) -> int | None:
    passages = "\n\n".join(
        f"[{c['location_label']}] {c['passage']}"
        for c in question["citations"]
        if c["passage"]
    )
    options = "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(question["options"]))
    result = provider.complete_json(
        model=JUDGE_MODEL,
        system=JUDGE_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Material:\n{passages}\n\n"
                f"Pregunta: {question['statement']}\n{options}",
            }
        ],
        temperature=0.0,
    )
    choice = str(result.data.get("opcion", "")).strip().upper()[:1]
    return LETTERS.index(choice) if choice and choice in LETTERS else None


def summary(drafts: list[dict], requested: int) -> dict:
    keys = [d["judge"] == d["key"] for d in drafts]
    return {
        "usable": round(len(drafts) / requested, 3) if requested else None,
        "key_confirmed": share(keys),
        "counts": {
            "usable": f"{len(drafts)}/{requested}",
            "key_confirmed": rate(keys),
        },
    }


def test_quiz_drafts(client, db, llm, teacher) -> None:
    settings = get_settings()
    provider = OpenAICompatProvider(
        OpenAI(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
            timeout=settings.llm_timeout_seconds * 3,
        )
    )
    by_subject: dict[str, list[dict]] = {}
    requested: dict[str, int] = {}
    for subject, content in available(subjects()):
        room = open_room(client, db, teacher, subject, content)
        drafts = []
        for topic in subject.data["questions"]:
            response = client.post(
                f"/v1/teacher/courses/{room.course_id}/topics/"
                f"{room.topic_ids[topic]}/questions/generate",
                headers=teacher.headers,
                json={"count": COUNT},
            )
            # A provider failure or timeout gives no usable draft.
            generated = (
                response.json()["questions"] if response.status_code == 201 else []
            )
            for question in generated:
                drafts.append(
                    {
                        "topic": topic,
                        "statement": question["statement"],
                        "options": question["options"],
                        "key": question["correct_option"],
                        "judge": judge(provider, question),
                    }
                )
        by_subject[subject.slug] = drafts
        requested[subject.slug] = COUNT * len(subject.data["questions"])

    model = model_label("questions")
    latency = llm.latency("questions")
    every = [d for drafts in by_subject.values() for d in drafts]
    rows = []
    for slug, drafts in by_subject.items():
        c = summary(drafts, requested[slug])["counts"]
        rows.append([slug, c["usable"], c["key_confirmed"]])
    c = summary(every, sum(requested.values()))["counts"]
    rows.append(["**all**", c["usable"], c["key_confirmed"]])
    disagreements = [
        [
            f"`{slug}`",
            d["statement"][:100].replace("\n", " "),
            " / ".join(f"{LETTERS[i]}) {o[:40]}" for i, o in enumerate(d["options"])),
            LETTERS[d["key"]],
            LETTERS[d["judge"]] if d["judge"] is not None else "—",
        ]
        for slug, drafts in by_subject.items()
        for d in drafts
        if d["judge"] != d["key"]
    ]
    lines = [
        f"Model `{model}`, judge `{JUDGE_MODEL}`, {COUNT} drafts per topic, median "
        f"{latency['median_ms']} ms per call.",
        "",
        *table(["Subject", "Usable drafts", "Key confirmed by the judge"], rows),
        "",
        "Judge disagrees (check by hand):",
        "",
        *table(["Subject", "Statement", "Options", "Key", "Judge"], disagreements),
    ]
    print("\n" + "\n".join(lines))
    write_results(
        "questions",
        model,
        {
            "judge": JUDGE_MODEL,
            "latency": latency,
            "overall": summary(every, sum(requested.values())),
            "by_subject": {
                slug: summary(d, requested[slug]) for slug, d in by_subject.items()
            },
            "drafts": by_subject,
        },
    )
