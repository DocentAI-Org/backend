"""US3 — teacher uploads, curates and validates course material (T2)."""

from pathlib import Path

from app.models import Document
from app.services.documents import recover_interrupted
from app.services.retrieval import retrieve
from tests.api.test_us2_courses import create_course
from tests.builders import build_pdf

FIXTURES = Path(__file__).parent.parent / "fixtures"
MARKDOWN = (FIXTURES / "ecuaciones.md").read_bytes()


def upload(client, teacher, course_id: str, name: str, content: bytes):
    return client.post(
        f"/v1/teacher/courses/{course_id}/documents",
        headers=teacher.headers,
        files={"file": (name, content, "application/octet-stream")},
    )


def uploaded_ready_document(client, teacher, course_id: str) -> dict:
    response = upload(client, teacher, course_id, "ecuaciones.md", MARKDOWN)
    assert response.status_code == 202, response.text
    document = client.get(
        f"/v1/teacher/courses/{course_id}/documents/{response.json()['id']}",
        headers=teacher.headers,
    ).json()
    assert document["processing_status"] == "ready", document
    return document


def validated_document(client, teacher, course_id: str) -> dict:
    document = uploaded_ready_document(client, teacher, course_id)
    response = client.post(
        f"/v1/teacher/courses/{course_id}/documents/{document['id']}/validate",
        headers=teacher.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_returns_processing_document_then_ready(
    client, teacher, storage
) -> None:
    course = create_course(client, teacher)

    response = upload(client, teacher, course["id"], "ecuaciones.md", MARKDOWN)

    assert response.status_code == 202
    accepted = response.json()
    assert accepted["processing_status"] == "processing"
    assert accepted["validation_status"] == "pending_validation"
    assert accepted["file_type"] == "markdown"
    assert accepted["size_bytes"] == len(MARKDOWN)
    assert len(storage.objects) == 1

    document = client.get(
        f"/v1/teacher/courses/{course['id']}/documents/{accepted['id']}",
        headers=teacher.headers,
    ).json()
    assert document["processing_status"] == "ready"
    assert document["page_count"] == 4
    assert document["fragment_count"] >= 4
    assert document["excluded_fragment_count"] == 0
    assert document["topics"] == []

    listed = client.get(
        f"/v1/teacher/courses/{course['id']}/documents", headers=teacher.headers
    ).json()
    assert [d["id"] for d in listed["items"]] == [accepted["id"]]


def test_pdf_fragments_carry_page_labels(client, teacher) -> None:
    course = create_course(client, teacher)
    content = build_pdf(["Ecuaciones de primer grado", "Sistemas de ecuaciones"])

    accepted = upload(client, teacher, course["id"], "tema.pdf", content).json()
    fragments = client.get(
        f"/v1/teacher/courses/{course['id']}/documents/{accepted['id']}/fragments",
        headers=teacher.headers,
    ).json()

    assert [f["location_label"] for f in fragments["items"]] == ["p. 1", "p. 2"]
    assert [f["position"] for f in fragments["items"]] == [1, 2]


def test_unsupported_type_and_size_are_rejected(client, teacher, storage) -> None:
    course = create_course(client, teacher)

    image = upload(client, teacher, course["id"], "foto.png", b"\x89PNG....")
    assert image.status_code == 415
    assert image.json()["error"]["code"] == "unsupported_file_type"

    too_big = b"a" * (20 * 1024 * 1024 + 1)
    big = upload(client, teacher, course["id"], "grande.md", too_big)
    assert big.status_code == 413
    assert big.json()["error"]["code"] == "file_too_large"

    assert storage.objects == {}


def test_unreadable_document_ends_in_error(client, teacher) -> None:
    course = create_course(client, teacher)

    accepted = upload(client, teacher, course["id"], "roto.pdf", b"not a pdf").json()
    document = client.get(
        f"/v1/teacher/courses/{course['id']}/documents/{accepted['id']}",
        headers=teacher.headers,
    ).json()

    assert document["processing_status"] == "error"
    assert document["error_reason"] == "unsupported_format"


def test_embedding_failure_ends_in_processing_failed(client, teacher, llm) -> None:
    course = create_course(client, teacher)
    llm.fail_embed = True

    accepted = upload(client, teacher, course["id"], "e.md", MARKDOWN).json()
    document = client.get(
        f"/v1/teacher/courses/{course['id']}/documents/{accepted['id']}",
        headers=teacher.headers,
    ).json()

    assert document["processing_status"] == "error"
    assert document["error_reason"] == "processing_failed"
    assert document["fragment_count"] == 0


def test_validate_exclude_and_revalidate(client, teacher) -> None:
    course = create_course(client, teacher)
    document = uploaded_ready_document(client, teacher, course["id"])
    base = f"/v1/teacher/courses/{course['id']}/documents/{document['id']}"

    validated = client.post(f"{base}/validate", headers=teacher.headers).json()
    assert validated["validation_status"] == "validated"
    assert validated["validated_by_name"] == "Prof. Elena Ruiz"
    assert validated["validated_at"] is not None

    excluded = client.post(f"{base}/exclude", headers=teacher.headers).json()
    assert excluded["validation_status"] == "excluded"

    again = client.post(f"{base}/validate", headers=teacher.headers).json()
    assert again["validation_status"] == "validated"


def test_document_must_be_ready_to_validate(client, teacher, llm) -> None:
    course = create_course(client, teacher)
    llm.fail_embed = True
    accepted = upload(client, teacher, course["id"], "e.md", MARKDOWN).json()

    response = client.post(
        f"/v1/teacher/courses/{course['id']}/documents/{accepted['id']}/validate",
        headers=teacher.headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


def test_only_non_excluded_fragments_of_validated_documents_are_retrievable(
    client, db, teacher, llm
) -> None:
    course = create_course(client, teacher)
    document = uploaded_ready_document(client, teacher, course["id"])
    base = f"/v1/teacher/courses/{course['id']}/documents/{document['id']}"
    question = "¿Cómo quito paréntesis con un signo menos delante?"

    # Pending validation: nothing is retrievable.
    assert retrieve(db, llm, course["id"], question, top_k=4, min_similarity=0) == []

    client.post(f"{base}/validate", headers=teacher.headers)
    hits = retrieve(db, llm, course["id"], question, top_k=1, min_similarity=0)
    assert hits and hits[0].fragment.location_label == "§ 3.3 Quitar paréntesis"

    fragment_id = str(hits[0].fragment.id)
    patched = client.patch(
        f"{base}/fragments/{fragment_id}",
        headers=teacher.headers,
        json={"excluded": True},
    )
    assert patched.status_code == 200
    assert patched.json()["excluded"] is True
    hits = retrieve(db, llm, course["id"], question, top_k=4, min_similarity=0)
    assert fragment_id not in {str(h.fragment.id) for h in hits}

    refreshed = client.get(base, headers=teacher.headers).json()
    assert refreshed["excluded_fragment_count"] == 1

    client.post(f"{base}/exclude", headers=teacher.headers)
    assert retrieve(db, llm, course["id"], question, top_k=4, min_similarity=0) == []


def test_delete_document_and_signed_url(client, teacher, storage) -> None:
    course = create_course(client, teacher)
    document = uploaded_ready_document(client, teacher, course["id"])
    base = f"/v1/teacher/courses/{course['id']}/documents/{document['id']}"

    signed = client.get(f"{base}/file-url", headers=teacher.headers)
    assert signed.status_code == 200
    assert signed.json()["url"].startswith("http://storage.test/signed/")
    assert signed.json()["expires_at"]

    deleted = client.delete(base, headers=teacher.headers)
    assert deleted.status_code == 204
    assert storage.objects == {}
    assert client.get(base, headers=teacher.headers).status_code == 404


def test_other_teacher_cannot_touch_documents(client, teacher, other_teacher) -> None:
    course = create_course(client, teacher)
    document = uploaded_ready_document(client, teacher, course["id"])
    base = f"/v1/teacher/courses/{course['id']}/documents/{document['id']}"

    for method, path in [
        ("get", base),
        ("post", f"{base}/validate"),
        ("get", f"{base}/fragments"),
        ("get", f"{base}/file-url"),
        ("delete", base),
    ]:
        response = client.request(method, path, headers=other_teacher.headers)
        assert response.status_code == 404, (method, path)

    upload_other = upload(client, other_teacher, course["id"], "x.md", MARKDOWN)
    assert upload_other.status_code == 404


def test_documents_interrupted_by_a_restart_are_flagged(client, db, teacher) -> None:
    course = create_course(client, teacher)
    document = uploaded_ready_document(client, teacher, course["id"])
    row = db.get(Document, document["id"])
    row.processing_status = "processing"
    db.commit()

    assert recover_interrupted(db) >= 1

    db.refresh(row)
    assert row.processing_status == "error"
    assert row.error_reason == "processing_interrupted"


def test_file_name_cannot_escape_the_document_storage_path(
    client, teacher, storage
) -> None:
    course = create_course(client, teacher)

    response = upload(client, teacher, course["id"], "../../otro/doc/evil.md", MARKDOWN)

    assert response.status_code == 202
    document = response.json()
    assert document["file_name"] == "evil.md"
    [path] = storage.objects
    assert path == f"{course['id']}/{document['id']}.md"
    assert ".." not in path


def test_nul_bytes_in_material_are_stripped(client, teacher) -> None:
    course = create_course(client, teacher)
    content = b"# Tema\n\nTexto con un car\x00acter nulo."

    accepted = upload(client, teacher, course["id"], "nulo.md", content).json()
    document = client.get(
        f"/v1/teacher/courses/{course['id']}/documents/{accepted['id']}",
        headers=teacher.headers,
    ).json()

    # NUL bytes are stripped, so the document still processes.
    assert document["processing_status"] == "ready"


def test_parser_crash_is_reported_not_left_processing(
    client, teacher, monkeypatch
) -> None:
    from app.services import documents

    def boom(*_args):
        raise RecursionError("pypdf went too deep")

    monkeypatch.setattr(documents, "parse_document", boom)
    course = create_course(client, teacher)

    accepted = upload(client, teacher, course["id"], "x.md", MARKDOWN).json()
    document = client.get(
        f"/v1/teacher/courses/{course['id']}/documents/{accepted['id']}",
        headers=teacher.headers,
    ).json()

    assert document["processing_status"] == "error"
    assert document["error_reason"] == "processing_failed"
