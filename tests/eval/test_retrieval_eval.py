"""Retrieval over each subject's material (specs/017 US2.1).

`uv run pytest -m eval -s tests/eval/test_retrieval_eval.py`. Needs only the embedding
model. The queries are the subject's tutor questions and retrieval queries (chat
threshold) and its feedback mistakes (statement and answer, exercise threshold), each
with the topics whose sections answer it. Off-material tutor questions should find
nothing over the threshold.
"""

import pytest

from app.core.config import get_settings
from app.services.retrieval import retrieve
from tests.eval.report import available, rate, share, table, write_results
from tests.eval.subjects import Room, open_room, subjects

pytestmark = [pytest.mark.eval, pytest.mark.db]


def queries(room: Room) -> list[dict]:
    settings = get_settings()
    data = room.subject.data
    chat = settings.retrieval_min_similarity
    found = [
        {"text": t["question"], "topics": t["topics"], "threshold": chat}
        for t in data["tutor"]
    ]
    found += [
        {"text": r["query"], "topics": r["topics"], "threshold": chat}
        for r in data["retrieval"]
    ]
    found += [
        {
            "text": f"{c['statement']}\n{c['answer']}",
            "topics": c["topics"],
            "threshold": settings.retrieval_min_similarity_exercises,
        }
        for c in data["feedback"]
        if c["topics"]
    ]
    return found


def measure(db, llm, room: Room) -> dict:
    top_k = get_settings().retrieval_top_k
    hits_at_k, reciprocal, answerable, rejected, notes = [], [], [], [], []
    for query in queries(room):
        hits = retrieve(db, llm, room.course_id, query["text"], top_k, -1.0)
        over = [h for h in hits if h.similarity >= query["threshold"]]
        label = query["text"].splitlines()[0][:70]
        if not query["topics"]:
            rejected.append(not over)
            if over:
                notes.append(f"«{label}» off-material, {over[0].similarity:.2f}")
            continue
        relevant = [
            bool(room.topics_of(h.fragment.section) & set(query["topics"]))
            for h in hits
        ]
        rank = next((i for i, ok in enumerate(relevant, start=1) if ok), None)
        hits_at_k.append(rank is not None)
        reciprocal.append(1 / rank if rank else 0.0)
        scores = [h.similarity for h, ok in zip(hits, relevant, strict=True) if ok]
        best = max(scores, default=None)
        answerable.append(best is not None and best >= query["threshold"])
        if best is None:
            notes.append(f"«{label}» not in the top {top_k}")
        elif best < query["threshold"]:
            notes.append(f"«{label}» {best:.2f} < {query['threshold']}")
    return {
        "hit_at_k": share(hits_at_k),
        "mrr": round(sum(reciprocal) / len(reciprocal), 3) if reciprocal else None,
        "answerable": share(answerable),
        "off_material_rejected": share(rejected),
        "counts": {
            "hit_at_k": rate(hits_at_k),
            "answerable": rate(answerable),
            "off_material_rejected": rate(rejected),
        },
        "notes": notes,
    }


def test_retrieval(client, db, llm, teacher) -> None:
    by_subject = {}
    for subject, content in available(subjects()):
        room = open_room(client, db, teacher, subject, content)
        by_subject[subject.slug] = measure(db, llm, room)

    settings = get_settings()
    rows = [
        [
            slug,
            m["counts"]["hit_at_k"],
            f"{m['mrr']:.2f}",
            m["counts"]["answerable"],
            m["counts"]["off_material_rejected"],
        ]
        for slug, m in by_subject.items()
    ]
    lines = [
        f"Embeddings `{settings.llm_embedding_model}`, top {settings.retrieval_top_k}.",
        "",
        *table(
            [
                "Subject",
                f"Hit@{settings.retrieval_top_k}",
                "MRR",
                "Over threshold",
                "Off-material rejected",
            ],
            rows,
        ),
    ]
    for slug, m in by_subject.items():
        if m["notes"]:
            lines.append(f"\n`{slug}`: " + "; ".join(m["notes"]))
    print("\n" + "\n".join(lines))
    write_results("retrieval", settings.llm_embedding_model, {"by_subject": by_subject})
