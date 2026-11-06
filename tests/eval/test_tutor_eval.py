"""Tutor replies on each subject (specs/017 US2.3).

`uv run pytest -m eval -s tests/eval/test_tutor_eval.py`. Each question is asked once,
in a new conversation, with the default `hints_first` policy and no solution requested.
It expects a kind (`answer`, `hint` for an exercise, `no_source` outside the material)
and, when it answers, a citation from one of the expected topics.
"""

import uuid

import pytest

from app.models import Fragment
from tests.api.helpers import ask, open_conversation
from tests.eval.report import (
    available,
    model_label,
    rate,
    share,
    table,
    write_results,
)
from tests.eval.subjects import Room, enrolled_student, open_room, subjects

pytestmark = [pytest.mark.eval, pytest.mark.db]


def cited_topics(db, room: Room, message: dict) -> set[str]:
    topics: set[str] = set()
    for citation in message["citations"]:
        if citation["fragment_id"]:
            fragment = db.get(Fragment, uuid.UUID(citation["fragment_id"]))
            topics |= room.topics_of(fragment.section)
    return topics


def summary(graded: list[dict]) -> dict:
    kinds = [g["kind_ok"] for g in graded]
    cites = [g["cite_ok"] for g in graded if g["cite_ok"] is not None]
    off = [g["kind_ok"] for g in graded if g["expect"] == ["no_source"]]
    hints = [g["kind_ok"] for g in graded if g["expect"] == ["hint"]]
    return {
        "kind": share(kinds),
        "citation": share(cites),
        "off_material": share(off),
        "exercise_hint": share(hints),
        "counts": {
            "kind": rate(kinds),
            "citation": rate(cites),
            "off_material": rate(off),
            "exercise_hint": rate(hints),
        },
    }


def test_tutor(client, db, llm, make_user, teacher) -> None:
    by_subject: dict[str, list[dict]] = {}
    for subject, content in available(subjects()):
        room = open_room(client, db, teacher, subject, content)
        student = enrolled_student(client, make_user, room)
        graded = []
        for item in subject.data["tutor"]:
            conversation = open_conversation(client, student, room.course_id)
            response = ask(
                client, student, room.course_id, conversation["id"], item["question"]
            )
            assert response.status_code == 201, response.text
            reply = response.json()["tutor_message"]
            cite_ok = None
            if item["topics"] and reply["kind"] in ("answer", "hint"):
                cite_ok = bool(cited_topics(db, room, reply) & set(item["topics"]))
            graded.append(
                {
                    "id": item["id"],
                    "expect": item["expect"],
                    "kind": reply["kind"],
                    "kind_ok": reply["kind"] in item["expect"],
                    "cite_ok": cite_ok,
                    "text": reply["text"],
                }
            )
        by_subject[subject.slug] = graded

    model = model_label("tutor")
    latency = llm.latency("tutor")
    every = [g for graded in by_subject.values() for g in graded]
    rows = []
    for slug, graded in [*by_subject.items(), ("**all**", every)]:
        c = summary(graded)["counts"]
        rows.append(
            [slug, c["kind"], c["citation"], c["exercise_hint"], c["off_material"]]
        )
    wrong = [
        [
            f"`{slug}/{g['id']}`",
            "/".join(g["expect"]),
            g["kind"],
            g["text"][:120].replace("\n", " "),
        ]
        for slug, graded in by_subject.items()
        for g in graded
        if not g["kind_ok"] or g["cite_ok"] is False
    ]
    lines = [
        f"Model `{model}`, {len(every)} questions, median {latency['median_ms']} ms "
        f"per call ({latency['calls']} calls).",
        "",
        *table(
            [
                "Subject",
                "Kind",
                "Citation",
                "Exercise → hint",
                "Off-material → no_source",
            ],
            rows,
        ),
        "",
        "Wrong kind or citation:",
        "",
        *table(["Question", "Expected", "Got", "Reply"], wrong),
    ]
    print("\n" + "\n".join(lines))
    write_results(
        "tutor",
        model,
        {
            "latency": latency,
            "overall": summary(every),
            "by_subject": {slug: summary(g) for slug, g in by_subject.items()},
            "replies": by_subject,
        },
    )
