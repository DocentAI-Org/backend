"""The local sample data (scripts/seed_dev.py) is consistent and parses as declared."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.chunking import chunk_sections
from app.services.parsing import parse_document
from scripts.seed_activity import BEHAVIOUR, SUPPLEMENT, Rng, Window, profile_of
from scripts.seed_material import (
    COURSE_KEYS,
    build_file,
    course_content,
    people,
    section_key,
)


def test_every_course_has_its_class_list_teacher_and_content() -> None:
    roster = people()
    teachers = {t["key"] for t in roster["teachers"]}
    groups = {g["key"] for g in roster["groups"]}
    assert sorted(c["key"] for c in roster["courses"]) == sorted(COURSE_KEYS)
    assert set(SUPPLEMENT) == set(COURSE_KEYS)
    for meta in roster["courses"]:
        assert meta["teacher"] in teachers
        assert meta["group"] in groups
        assert course_content(meta["key"])["key"] == meta["key"]
    emails = {s["email"] for g in roster["groups"] for s in g["students"]}
    assert "alumno@docentai.local" in emails


@pytest.mark.parametrize("key", COURSE_KEYS)
def test_documents_parse_into_the_declared_sections(key: str) -> None:
    content = course_content(key)
    for document in content["documents"]:
        parsed = parse_document(
            document["file_type"], build_file(content["name"], document)
        )
        expected = [section_key(document, s) for s in document["sections"]]
        assert [s.section for s in parsed.sections] == expected
        # One fragment per section, so a topic cites the whole section.
        assert len(chunk_sections(parsed.sections)) == len(expected)
        if document["file_type"] == "pdf":
            assert parsed.page_count == document["page_count"]


@pytest.mark.parametrize("key", COURSE_KEYS)
def test_topics_point_to_sections_of_the_main_documents(key: str) -> None:
    content = course_content(key)
    main = {d["file_name"]: d for d in content["documents"][:2]}
    for topic in content["topics"]:
        titles = [s["title"] for s in main[topic["document"]]["sections"]]
        assert topic["section"] in titles
        assert topic["quiz"] and topic["exercises"] and topic["questions"]


def test_pdf_text_keeps_spanish_accents() -> None:
    document = {
        "file_type": "pdf",
        "page_count": 2,
        "sections": [{"title": "1.1 Ecuación", "page": 2, "text": "Raíz: √9 = 3."}],
    }
    parsed = parse_document("pdf", build_file("Álgebra", document))
    assert parsed.sections[0].section == "2"
    assert "1.1 Ecuación" in parsed.sections[0].text
    assert "raíz de 9" in parsed.sections[0].text


def test_the_random_profiles_are_the_same_on_every_run() -> None:
    first = [profile_of(Rng(f"trait:{n}@example.org")) for n in range(50)]
    again = [profile_of(Rng(f"trait:{n}@example.org")) for n in range(50)]
    assert first == again
    assert {"engaged", "regular", "struggling"} <= set(first)


def test_activity_is_never_dated_in_the_future() -> None:
    now = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    window = Window(
        Rng("w"),
        None,  # type: ignore[arg-type]  # during() reads neither course nor student
        None,  # type: ignore[arg-type]
        BEHAVIOUR["regular"],
        start=now - timedelta(days=3),
        end=now,
        now=now,
    )
    assert all(window.during(now) < now for _ in range(100))
