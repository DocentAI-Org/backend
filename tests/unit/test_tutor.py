from decimal import Decimal

from app.core.config import Settings
from app.services.interactions import estimate_cost, student_ref
from app.services.tutor import ground_reply


def test_ground_reply_keeps_known_citations_in_order() -> None:
    reply = ground_reply(
        {"kind": "answer", "text": "Respuesta", "cited": ["F2", "F1", "F2"]}, 3
    )

    assert reply.kind == "answer"
    assert reply.text == "Respuesta"
    assert reply.cited_indexes == [1, 0]


def test_ground_reply_without_valid_citations_is_no_source() -> None:
    for data in [
        {"kind": "answer", "text": "x", "cited": []},
        {"kind": "answer", "text": "x", "cited": ["F7"]},
        {"kind": "answer", "text": "x"},
        {"kind": "hint", "text": "x", "cited": "F1"},
        {},
        {"kind": "no_source", "text": "x", "cited": ["F1"]},
        {"kind": "poem", "text": "x", "cited": ["F1"]},
        {"kind": "answer", "text": "", "cited": ["F1"]},
    ]:
        assert ground_reply(data, 2).kind == "no_source", data


def test_cost_estimate_uses_configured_prices() -> None:
    settings = Settings(llm_price_input_per_mtok=0.5, llm_price_output_per_mtok=1.5)

    assert estimate_cost(settings, 1_000_000, 2_000_000) == Decimal("3.5")
    assert estimate_cost(Settings(), 1000, 1000) == Decimal("0")


def test_student_ref_is_a_stable_keyed_hash() -> None:
    settings = Settings(log_pseudonym_secret="secret-a")
    other = Settings(log_pseudonym_secret="secret-b")

    ref = student_ref(settings, "11111111-1111-1111-1111-111111111111")

    assert ref == student_ref(settings, "11111111-1111-1111-1111-111111111111")
    assert ref != student_ref(other, "11111111-1111-1111-1111-111111111111")
    assert len(ref) == 64
