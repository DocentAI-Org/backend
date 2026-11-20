"""025 — each AI quiz draft is solved without its key, and disagreements are flagged."""

import pytest

from app.core.config import get_settings
from app.llm.client import LLMError
from tests.api.test_quiz_questions import (
    DRAFTS,
    edit,
    generated,
    generation_logs,
    questions_path,
)


def answering(*answers) -> object:
    """Drafts for the drafting call; `answers` for the check, which lists questions."""
    check = {"answers": list(answers)}

    def reply(_system: str, messages: list[dict[str, str]]) -> dict:
        return check if "<preguntas>" in messages[-1]["content"] else DRAFTS

    return reply


# The drafts keep "2x - 6" right, moved to A, B and C in turn.
CHECK = answering(
    {"question": 1, "right": ["A"]},
    {"question": 2, "right": ["A"]},
    {"question": 3, "right": ["a", " C"]},
)


def test_each_draft_gets_its_key_check(client, llm, teacher, student) -> None:
    _, _, made = generated(client, llm, teacher, student, CHECK)

    assert [(q["key_check"], q["key_check_options"]) for q in made] == [
        ("agrees", [0]),
        ("disagrees", [0]),
        ("several", [0, 2]),
    ]


def test_the_check_sees_no_keys_and_uses_the_course_model(
    client, llm, teacher, student
) -> None:
    generated(client, llm, teacher, student, CHECK)

    assert len(llm.chat_calls) == 2
    _, messages = llm.chat_calls[-1]
    content = messages[-1]["content"]
    assert "¿Cuánto vale 2(x - 3) sin paréntesis?" in content
    assert "A) " in content and "2x - 6" in content
    assert "El 2 multiplica" not in content  # the explanation
    assert '"correct"' not in content
    assert "Quitar paréntesis" in content  # the same material
    assert llm.tasks[-1] == "questions"
    assert llm.temperatures[-1] == 0.0
    assert llm.routes[-1] == llm.routes[0]


def test_a_failed_check_keeps_the_drafts_unchecked(
    client, llm, teacher, student
) -> None:
    def reply(_system: str, messages: list[dict[str, str]]) -> dict:
        if "<preguntas>" in messages[-1]["content"]:
            raise LLMError("check failed")
        return DRAFTS

    _, _, made = generated(client, llm, teacher, student, reply)

    assert len(made) == 3
    assert {(q["key_check"], tuple(q["key_check_options"])) for q in made} == {
        (None, ())
    }


@pytest.mark.parametrize(
    "answers",
    [
        (),
        ({"question": 1, "right": []},),
        ({"question": 1, "right": ["Z"]}, {"question": 9, "right": ["A"]}),
    ],
)
def test_unusable_answers_leave_their_drafts_unchecked(
    client, llm, teacher, student, answers
) -> None:
    _, _, made = generated(client, llm, teacher, student, answering(*answers))

    assert [q["key_check"] for q in made] == [None, None, None]


def test_only_usable_answers_are_kept(client, llm, teacher, student) -> None:
    reply = answering({"question": 2, "right": ["B"]}, {"question": 3, "right": "C"})

    _, _, made = generated(client, llm, teacher, student, reply)

    assert [q["key_check"] for q in made] == [None, "agrees", "agrees"]


def test_the_check_can_be_turned_off(
    client, llm, teacher, student, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "quiz_key_check", False)

    _, _, made = generated(client, llm, teacher, student, CHECK)

    assert len(llm.chat_calls) == 1
    assert [q["key_check"] for q in made] == [None, None, None]


def test_the_log_counts_both_calls(client, db, llm, teacher, student) -> None:
    room, _, _ = generated(client, llm, teacher, student, CHECK)

    [log] = generation_logs(db, room.course_id)
    # The fake model answers 20 output tokens per call.
    assert log.output_tokens == 40


def test_flagged_drafts_come_first_among_the_pending(
    client, llm, teacher, student
) -> None:
    reply = answering(
        {"question": 1, "right": ["B"]},
        {"question": 2, "right": ["B"]},
        {"question": 3, "right": ["C"]},
    )
    room, _, made = generated(client, llm, teacher, student, reply)
    edit(client, teacher, room.course_id, made[2]["id"], status="approved")

    listed = client.get(questions_path(room.course_id), headers=teacher.headers).json()

    # Newest first otherwise: the flagged first draft leads, the approved one is last.
    assert [q["id"] for q in listed["items"]] == [
        made[0]["id"],
        made[1]["id"],
        made[2]["id"],
    ]
    assert listed["items"][0]["key_check"] == "disagrees"


def test_editing_the_options_or_key_clears_the_check(
    client, llm, teacher, student
) -> None:
    room, _, made = generated(client, llm, teacher, student, CHECK)
    flagged = made[1]

    kept = edit(
        client, teacher, room.course_id, flagged["id"], explanation="Otra razón."
    ).json()
    assert kept["key_check"] == "disagrees"
    approved = edit(
        client, teacher, room.course_id, flagged["id"], status="approved"
    ).json()
    assert approved["key_check"] == "disagrees"

    fixed = edit(client, teacher, room.course_id, flagged["id"], correct_option=0)
    assert fixed.json()["key_check"] is None
    assert fixed.json()["key_check_options"] == []
    other = edit(
        client,
        teacher,
        room.course_id,
        made[2]["id"],
        options=["2x - 6", "2x - 5", "2x - 7", "2x - 8"],
    ).json()
    assert other["key_check"] is None
