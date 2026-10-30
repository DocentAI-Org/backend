"""US3 (spec 003) — the error taxonomy is readable by anyone signed in."""


def test_signed_in_users_read_the_provisional_taxonomy(
    client, student, teacher
) -> None:
    for user in (student, teacher):
        response = client.get("/v1/error-types", headers=user.headers)
        assert response.status_code == 200, response.text

    taxonomy = response.json()
    assert taxonomy["provisional"] is True
    codes = [t["code"] for t in taxonomy["items"]]
    assert codes == [
        "comprehension",
        "conceptual",
        "procedural",
        "execution",
        "incomplete",
        "expression",
    ]
    first = taxonomy["items"][0]
    assert first["label"] == {
        "es": "Comprensión del enunciado",
        "en": "Understanding the task",
    }
    assert first["description"]["es"] and first["description"]["en"]


def test_the_taxonomy_needs_a_session(client) -> None:
    assert client.get("/v1/error-types").status_code == 401
