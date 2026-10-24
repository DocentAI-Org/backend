from pathlib import Path

import pytest

from app.services.parsing import ParsingError, detect_file_type, parse_document
from tests.builders import build_docx, build_pdf

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("tema.pdf", "pdf"),
        ("Tema.DOCX", "docx"),
        ("notas.md", "markdown"),
        ("notas.markdown", "markdown"),
        ("foto.png", None),
        ("sin-extension", None),
    ],
)
def test_file_type_comes_from_the_extension(name: str, expected: str | None) -> None:
    assert detect_file_type(name) == expected


def test_pdf_has_one_section_per_page_labelled_by_page() -> None:
    content = build_pdf(["Primera pagina sobre ecuaciones", "Segunda pagina"])

    parsed = parse_document("pdf", content)

    assert parsed.page_count == 2
    assert [s.location_label for s in parsed.sections] == ["p. 1", "p. 2"]
    assert [s.section for s in parsed.sections] == ["1", "2"]
    assert "ecuaciones" in parsed.sections[0].text


def test_markdown_sections_follow_headings() -> None:
    content = (FIXTURES / "ecuaciones.md").read_bytes()

    parsed = parse_document("markdown", content)

    labels = [s.location_label for s in parsed.sections]
    assert labels == [
        "§ Tema 3: Ecuaciones de primer grado",
        "§ 3.1 Transponer términos",
        "§ 3.2 Despejar la incógnita",
        "§ 3.3 Quitar paréntesis",
    ]
    assert parsed.page_count == 4
    assert "se resta 3" in parsed.sections[1].text


def test_docx_sections_follow_heading_styles() -> None:
    content = build_docx(
        [
            ("", "Texto previo al primer título."),
            ("Heading 1", "Fracciones"),
            ("", "Una fracción representa partes de un todo."),
            ("Heading 2", "Suma de fracciones"),
            ("", "Se busca un denominador común."),
        ]
    )

    parsed = parse_document("docx", content)

    assert [s.section for s in parsed.sections] == [
        "Inicio",
        "Fracciones",
        "Suma de fracciones",
    ]
    assert parsed.sections[2].text == "Se busca un denominador común."


def test_document_without_text_is_rejected() -> None:
    with pytest.raises(ParsingError) as error:
        parse_document("markdown", b"   \n\n")
    assert error.value.reason == "no_readable_text"


@pytest.mark.parametrize("file_type", ["pdf", "docx"])
def test_corrupt_binary_files_are_unsupported(file_type: str) -> None:
    with pytest.raises(ParsingError) as error:
        parse_document(file_type, b"this is not a real file")
    assert error.value.reason == "unsupported_format"
