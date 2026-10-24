from app.services.chunking import chunk_sections
from app.services.parsing import Section


def test_short_section_becomes_one_fragment() -> None:
    sections = [Section("1", "p. 1", "Párrafo uno.\n\nPárrafo dos.")]

    chunks = chunk_sections(sections, max_chars=1200)

    assert len(chunks) == 1
    assert chunks[0].text == "Párrafo uno.\n\nPárrafo dos."
    assert chunks[0].location_label == "p. 1"


def test_paragraphs_are_merged_up_to_the_limit_and_never_across_sections() -> None:
    paragraph = "palabra " * 40  # ~320 characters
    sections = [
        Section("A", "§ A", "\n\n".join([paragraph] * 5)),
        Section("B", "§ B", paragraph),
    ]

    chunks = chunk_sections(sections, max_chars=700)

    assert all(len(c.text) <= 700 for c in chunks)
    assert [c.section for c in chunks] == ["A", "A", "A", "B"]


def test_oversized_paragraph_is_split_on_sentences() -> None:
    long_paragraph = " ".join(f"Frase número {i} sobre álgebra." for i in range(80))

    chunks = chunk_sections([Section("1", "p. 1", long_paragraph)], max_chars=300)

    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)
    assert " ".join(c.text for c in chunks).count("Frase número") == 80


def test_empty_sections_produce_no_fragments() -> None:
    assert chunk_sections([Section("1", "p. 1", "   ")], max_chars=500) == []
