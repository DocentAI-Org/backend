import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

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


BODY = 10.0
TITLE = 16.0


def _labels(content: bytes) -> list[tuple[str, str]]:
    return [
        (s.section, s.location_label) for s in parse_document("pdf", content).sections
    ]


def test_pdf_sections_follow_its_outline() -> None:
    content = build_pdf(
        [
            [
                (BODY, "Ecuaciones lineales"),
                (BODY, "Una ecuacion lineal tiene grado uno."),
            ],
            [(BODY, "Mas ejemplos de ecuaciones.")],
            [(BODY, "Sistemas"), (BODY, "Dos ecuaciones con dos incognitas.")],
        ],
        outline=[("Ecuaciones lineales", 0), ("Sistemas", 2)],
    )

    assert _labels(content) == [
        ("Ecuaciones lineales", "§ Ecuaciones lineales, p. 1"),
        ("Ecuaciones lineales", "§ Ecuaciones lineales, p. 2"),
        ("Sistemas", "§ Sistemas, p. 3"),
    ]


def test_pdf_outline_under_a_single_title_uses_the_next_level() -> None:
    content = build_pdf(
        [[(BODY, "Libro")], [(BODY, "Capitulo uno")], [(BODY, "Capitulo dos")]],
    )
    reader = PdfReader(io.BytesIO(content))
    writer = PdfWriter(clone_from=reader)
    book = writer.add_outline_item(title="Libro", page_number=0)
    writer.add_outline_item(title="Capitulo uno", page_number=1, parent=book)
    writer.add_outline_item(title="Capitulo dos", page_number=2, parent=book)
    out = io.BytesIO()
    writer.write(out)

    assert [name for name, _ in _labels(out.getvalue())] == [
        "Inicio",
        "Capitulo uno",
        "Capitulo dos",
    ]


def test_pdf_sections_follow_headings_set_larger_than_the_body() -> None:
    content = build_pdf(
        [
            [(BODY, "Texto antes del primer titulo.")],
            [
                (TITLE, "Fracciones"),
                (BODY, "Una fraccion representa partes de un todo."),
            ],
            [
                (BODY, "Fracciones equivalentes."),
                (TITLE, "Decimales"),
                (BODY, "Un decimal."),
            ],
        ]
    )

    parsed = parse_document("pdf", content)

    assert [(s.section, s.location_label) for s in parsed.sections] == [
        ("Inicio", "§ Inicio, p. 1"),
        ("Fracciones", "§ Fracciones, p. 2"),
        ("Fracciones", "§ Fracciones, p. 3"),
        ("Decimales", "§ Decimales, p. 3"),
    ]
    # A section that starts mid-page leaves the text above it to the previous one.
    assert parsed.sections[2].text == "Fracciones equivalentes."
    assert parsed.sections[3].text == "Decimales\nUn decimal."
    assert parsed.page_count == 3


def test_pdf_heading_over_two_lines_is_one_heading() -> None:
    body = (BODY, "Una ecuacion de primer grado tiene la incognita elevada a uno.")
    content = build_pdf(
        [
            [(TITLE, "Ecuaciones de primer grado"), (TITLE, "con una incognita"), body],
            [(TITLE, "Sistemas"), body, body],
        ]
    )

    assert _labels(content)[0][0] == "Ecuaciones de primer grado con una incognita"


def test_pdf_repeated_headings_are_numbered() -> None:
    content = build_pdf(
        [
            [(TITLE, "Ejercicios"), (BODY, "Primeros ejercicios.")],
            [(TITLE, "Teoria"), (BODY, "Explicacion.")],
            [(TITLE, "Ejercicios"), (BODY, "Mas ejercicios.")],
        ]
    )

    assert [name for name, _ in _labels(content)] == [
        "Ejercicios",
        "Teoria",
        "Ejercicios (2)",
    ]


def test_pdf_running_header_is_not_a_heading() -> None:
    header = (TITLE, "Matematicas 3 ESO")
    content = build_pdf(
        [
            [header, (BODY, "Primera pagina.")],
            [header, (BODY, "Segunda pagina.")],
            [header, (BODY, "Tercera pagina.")],
        ]
    )

    assert [name for name, _ in _labels(content)] == ["1", "2", "3"]


def test_pdf_with_one_larger_line_keeps_its_pages() -> None:
    # A cover title is not a structure: two headings are needed.
    content = build_pdf(
        [[(TITLE, "Portada"), (BODY, "Texto.")], [(BODY, "Mas texto.")]]
    )

    assert _labels(content) == [("1", "p. 1"), ("2", "p. 2")]


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
