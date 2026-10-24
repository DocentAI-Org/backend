"""US6 — teacher defines course topics and assigns material to them (T9)."""

import uuid

from app.models import TopicAssignment
from tests.api.test_us2_courses import create_course
from tests.api.test_us3_material import validated_document


def create_topic(client, teacher, course_id: str, name: str):
    return client.post(
        f"/v1/teacher/courses/{course_id}/topics",
        headers=teacher.headers,
        json={"name": name},
    )


def test_topic_crud_and_order(client, teacher) -> None:
    course = create_course(client, teacher)
    base = f"/v1/teacher/courses/{course['id']}/topics"

    first = create_topic(client, teacher, course["id"], "Ecuaciones").json()
    second = create_topic(client, teacher, course["id"], "Paréntesis").json()
    assert (first["position"], second["position"]) == (1, 2)
    assert first["assignment_count"] == 0

    renamed = client.patch(
        f"{base}/{first['id']}", headers=teacher.headers, json={"name": "Ecuaciones I"}
    )
    assert renamed.json()["name"] == "Ecuaciones I"

    reordered = client.put(
        f"{base}/order",
        headers=teacher.headers,
        json={"topic_ids": [second["id"], first["id"]]},
    ).json()
    assert [t["name"] for t in reordered] == ["Paréntesis", "Ecuaciones I"]

    listed = client.get(base, headers=teacher.headers).json()
    assert [t["position"] for t in listed] == [1, 2]

    deleted = client.delete(f"{base}/{second['id']}", headers=teacher.headers)
    assert deleted.status_code == 204
    assert [t["name"] for t in client.get(base, headers=teacher.headers).json()] == [
        "Ecuaciones I"
    ]


def test_topic_names_are_unique_and_validated(client, teacher) -> None:
    course = create_course(client, teacher)
    create_topic(client, teacher, course["id"], "Ecuaciones")

    duplicate = create_topic(client, teacher, course["id"], "ecuaciones")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "topic_name_taken"

    for name in ("", "x" * 61):
        assert create_topic(client, teacher, course["id"], name).status_code == 422


def test_order_must_list_every_topic(client, teacher) -> None:
    course = create_course(client, teacher)
    topic = create_topic(client, teacher, course["id"], "Uno").json()
    create_topic(client, teacher, course["id"], "Dos")

    response = client.put(
        f"/v1/teacher/courses/{course['id']}/topics/order",
        headers=teacher.headers,
        json={"topic_ids": [topic["id"]]},
    )

    assert response.status_code == 422


def test_assignments_and_unassigned_material(client, db, teacher) -> None:
    course = create_course(client, teacher)
    document = validated_document(client, teacher, course["id"])
    topic = create_topic(client, teacher, course["id"], "Ecuaciones").json()
    other = create_topic(client, teacher, course["id"], "Paréntesis").json()
    base = f"/v1/teacher/courses/{course['id']}"

    unassigned = client.get(f"{base}/unassigned-material", headers=teacher.headers)
    sections = unassigned.json()[0]["sections"]
    assert unassigned.json()[0]["document_id"] == document["id"]
    assert "3.3 Quitar paréntesis" in sections

    created = client.post(
        f"{base}/topic-assignments",
        headers=teacher.headers,
        json={
            "topic_id": topic["id"],
            "document_id": document["id"],
            "section": "3.1 Transponer términos",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "confirmed"
    assert created.json()["document_name"] == "ecuaciones.md"

    # A system suggestion stays "suggested" until the teacher acts on it.
    suggestion = TopicAssignment(
        course_id=uuid.UUID(course["id"]),
        topic_id=uuid.UUID(topic["id"]),
        document_id=uuid.UUID(document["id"]),
        section="3.3 Quitar paréntesis",
        status="suggested",
    )
    db.add(suggestion)
    db.commit()
    suggested = client.get(
        f"{base}/topic-assignments?status=suggested", headers=teacher.headers
    ).json()
    assert [a["id"] for a in suggested] == [str(suggestion.id)]
    sections = client.get(f"{base}/unassigned-material", headers=teacher.headers)
    assert "3.3 Quitar paréntesis" in sections.json()[0]["sections"]

    confirmed = client.patch(
        f"{base}/topic-assignments/{suggestion.id}",
        headers=teacher.headers,
        json={"topic_id": other["id"], "status": "confirmed"},
    ).json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["topic_name"] == "Paréntesis"

    remaining = client.get(f"{base}/unassigned-material", headers=teacher.headers)
    sections = remaining.json()[0]["sections"]
    assert "3.1 Transponer términos" not in sections
    assert "3.3 Quitar paréntesis" not in sections

    whole = client.post(
        f"{base}/topic-assignments",
        headers=teacher.headers,
        json={"topic_id": topic["id"], "document_id": document["id"]},
    )
    assert whole.status_code == 201
    assert (
        client.get(f"{base}/unassigned-material", headers=teacher.headers).json() == []
    )
    detail = client.get(
        f"{base}/documents/{document['id']}", headers=teacher.headers
    ).json()
    assert {t["name"] for t in detail["topics"]} == {"Ecuaciones", "Paréntesis"}

    removed = client.delete(
        f"{base}/topic-assignments/{whole.json()['id']}", headers=teacher.headers
    )
    assert removed.status_code == 204


def test_assignment_targets_must_belong_to_the_course(
    client, teacher, other_teacher
) -> None:
    course = create_course(client, teacher)
    foreign = create_course(client, other_teacher, "Ajeno")
    foreign_doc = validated_document(client, other_teacher, foreign["id"])
    topic = create_topic(client, teacher, course["id"], "Ecuaciones").json()

    response = client.post(
        f"/v1/teacher/courses/{course['id']}/topic-assignments",
        headers=teacher.headers,
        json={"topic_id": topic["id"], "document_id": foreign_doc["id"]},
    )

    assert response.status_code == 404
