"""024 — a suggested topic for each section of the material (FR-073 of spec 001)."""

import pytest

from app.core.config import get_settings
from tests.api.test_us2_courses import create_course
from tests.api.test_us3_material import upload
from tests.api.test_us6_topics import create_topic

MATERIAL = b"""# Fracciones

Las fracciones tienen numerador y denominador.
Sumar fracciones pide un denominador comun.

# Decimales

Los decimales llevan coma. Redondear decimales quita cifras a los decimales.

# Mezcla

El tiempo de hoy: lluvia por la tarde y viento del norte.
"""


@pytest.fixture(autouse=True)
def _threshold(monkeypatch) -> None:
    # The fake embeddings are bags of words: one shared word gives about 0.5.
    monkeypatch.setattr(get_settings(), "topic_suggestion_min_similarity", 0.3)


def _document(client, teacher, course_id: str) -> dict:
    response = upload(client, teacher, course_id, "numeros.md", MATERIAL)
    assert response.status_code == 202, response.text
    return response.json()


def _suggested(client, teacher, course_id: str) -> dict[str, str]:
    """Section -> suggested topic name."""
    rows = client.get(
        f"/v1/teacher/courses/{course_id}/topic-assignments?status=suggested",
        headers=teacher.headers,
    ).json()
    return {row["section"]: row["topic_name"] for row in rows}


def _pending(client, teacher, course_id: str, document_id: str) -> int:
    return client.get(
        f"/v1/teacher/courses/{course_id}/documents/{document_id}",
        headers=teacher.headers,
    ).json()["suggested_sections"]


def test_each_section_gets_its_closest_topic_after_processing(client, teacher) -> None:
    course = create_course(client, teacher)
    create_topic(client, teacher, course["id"], "Fracciones")
    create_topic(client, teacher, course["id"], "Decimales")

    document = _document(client, teacher, course["id"])

    # "Mezcla" is close to no topic and gets no suggestion.
    assert _suggested(client, teacher, course["id"]) == {
        "Fracciones": "Fracciones",
        "Decimales": "Decimales",
    }
    assert _pending(client, teacher, course["id"], document["id"]) == 2


def test_no_suggestion_below_the_threshold_or_without_topics(
    client, teacher, monkeypatch
) -> None:
    course = create_course(client, teacher)
    document = _document(client, teacher, course["id"])
    assert _suggested(client, teacher, course["id"]) == {}
    assert _pending(client, teacher, course["id"], document["id"]) == 0

    monkeypatch.setattr(get_settings(), "topic_suggestion_min_similarity", 0.99)
    create_topic(client, teacher, course["id"], "Fracciones")

    assert _suggested(client, teacher, course["id"]) == {}


def test_suggestions_follow_new_and_renamed_topics(client, teacher) -> None:
    course = create_course(client, teacher)
    _document(client, teacher, course["id"])

    topic = create_topic(client, teacher, course["id"], "Fracciones").json()
    assert _suggested(client, teacher, course["id"]) == {"Fracciones": "Fracciones"}

    renamed = client.patch(
        f"/v1/teacher/courses/{course['id']}/topics/{topic['id']}",
        headers=teacher.headers,
        json={"name": "Decimales"},
    )
    assert renamed.status_code == 200
    assert _suggested(client, teacher, course["id"]) == {"Decimales": "Decimales"}


def test_confirmed_assignments_are_never_touched(client, teacher) -> None:
    course = create_course(client, teacher)
    base = f"/v1/teacher/courses/{course['id']}"
    fractions = create_topic(client, teacher, course["id"], "Fracciones").json()
    decimals = create_topic(client, teacher, course["id"], "Decimales").json()
    document = _document(client, teacher, course["id"])
    suggestion = next(
        row
        for row in client.get(
            f"{base}/topic-assignments", headers=teacher.headers
        ).json()
        if row["section"] == "Fracciones"
    )

    # The teacher corrects the suggestion; a new topic recomputes the others only.
    client.patch(
        f"{base}/topic-assignments/{suggestion['id']}",
        headers=teacher.headers,
        json={"topic_id": decimals["id"], "status": "confirmed"},
    )
    create_topic(client, teacher, course["id"], "Redondear cifras")

    rows = client.get(f"{base}/topic-assignments", headers=teacher.headers).json()
    fractions_rows = [row for row in rows if row["section"] == "Fracciones"]
    assert [(r["topic_id"], r["status"]) for r in fractions_rows] == [
        (decimals["id"], "confirmed")
    ]
    assert fractions["id"] not in {r["topic_id"] for r in fractions_rows}
    assert _pending(client, teacher, course["id"], document["id"]) == 1


def test_a_whole_document_assignment_leaves_nothing_to_suggest(client, teacher) -> None:
    course = create_course(client, teacher)
    base = f"/v1/teacher/courses/{course['id']}"
    document = _document(client, teacher, course["id"])
    topic = create_topic(client, teacher, course["id"], "Numeros").json()
    client.post(
        f"{base}/topic-assignments",
        headers=teacher.headers,
        json={"topic_id": topic["id"], "document_id": document["id"]},
    )

    create_topic(client, teacher, course["id"], "Fracciones")

    assert _suggested(client, teacher, course["id"]) == {}


@pytest.mark.parametrize("chosen", ["Fracciones", "Decimales"])
def test_a_manual_assignment_replaces_the_suggestion(client, teacher, chosen) -> None:
    course = create_course(client, teacher)
    base = f"/v1/teacher/courses/{course['id']}"
    topics = {
        name: create_topic(client, teacher, course["id"], name).json()["id"]
        for name in ("Fracciones", "Decimales")
    }
    document = _document(client, teacher, course["id"])

    created = client.post(
        f"{base}/topic-assignments",
        headers=teacher.headers,
        json={
            "topic_id": topics[chosen],
            "document_id": document["id"],
            "section": "Fracciones",
        },
    )

    assert created.status_code == 201, created.text
    assert _suggested(client, teacher, course["id"]) == {"Decimales": "Decimales"}


def test_a_topic_is_saved_when_the_embeddings_fail(client, teacher, llm) -> None:
    course = create_course(client, teacher)
    _document(client, teacher, course["id"])
    llm.fail_embed = True

    response = create_topic(client, teacher, course["id"], "Fracciones")

    assert response.status_code == 201
    assert _suggested(client, teacher, course["id"]) == {}
