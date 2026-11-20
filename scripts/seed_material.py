"""Course material and class lists of the local sample data (scripts/seed_data/).

The JSON files are shared, unchanged, with the frontend's demo deployment
(`tests/app/mock-api/demo-data/`). This module reads them and builds each document as
a real file of its declared type, laid out so the app's parser (app/services/parsing.py)
finds the sections the data declares: a heading per section in DOCX and Markdown, the
section on its own page in a PDF (the parser names PDF sections by page number).
"""

import io
import json
import textwrap
from functools import cache
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument

DATA_DIR = Path(__file__).resolve().parent / "seed_data"

# Course content in creation order: Álgebra last, so it heads the "most recent" lists.
COURSE_KEYS = [
    "calculo-uni",
    "programacion-uni",
    "bases-datos-uni",
    "contemporanea-4a",
    "edad-moderna-3b",
    "siglo-de-oro-4a",
    "comentario-4a",
    "lengua-3b",
    "estadistica-4a",
    "funciones-4a",
    "geometria-3b",
    "algebra-3b",
]

# The standard PDF fonts only cover Windows-1252: what they cannot show is spelled out.
_PDF_FALLBACK = {
    "−": "-",
    "√": "raíz de ",
    "→": "->",
    "ℝ": "R",
    "∞": "infinito",
    "₁": "1",
    "₂": "2",
    "π": "pi",
    "≥": ">=",
    "≤": "<=",
    "∈": "en",
    "∫": "integral de ",
    "≈": "~",
    "Ā": "A",
}
_PDF_LINE_CHARS = 92


@cache
def people() -> dict[str, Any]:
    return json.loads((DATA_DIR / "people.json").read_text(encoding="utf-8"))


@cache
def course_content(key: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / f"{key}.json").read_text(encoding="utf-8"))


def section_key(document: dict[str, Any], section: dict[str, Any]) -> str:
    """The `section` the app stores for this section's fragments."""
    return str(section["page"]) if document["file_type"] == "pdf" else section["title"]


def build_file(course_name: str, document: dict[str, Any]) -> bytes:
    """The document as a file of its declared type."""
    sections = document["sections"]
    if document["file_type"] == "pdf":
        pages = {s["page"]: [s["title"], s["text"]] for s in sections}
        return build_pdf(pages, max(document["page_count"] or 1, *pages))
    if document["file_type"] == "docx":
        return build_docx(course_name, sections)
    body = "".join(f"## {s['title']}\n\n{s['text']}\n\n" for s in sections)
    return f"# {course_name}\n\n{body}".encode()


def build_docx(title: str, sections: list[dict[str, Any]]) -> bytes:
    document = DocxDocument()
    document.add_heading(title, level=0)  # "Title": a heading with no text of its own
    for section in sections:
        document.add_heading(section["title"], level=1)
        document.add_paragraph(section["text"])
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _pdf_text(text: str) -> str:
    for char, spelled in _PDF_FALLBACK.items():
        text = text.replace(char, spelled)
    text = text.encode("cp1252", errors="replace").decode("cp1252")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(title: str, text: str) -> bytes:
    lines = textwrap.wrap(_pdf_text(text), _PDF_LINE_CHARS)
    body = " ".join(f"({line}) '" for line in lines)
    return (
        f"BT /F2 13 Tf 72 740 Td ({_pdf_text(title)}) Tj "
        f"/F1 11 Tf 15 TL 0 -10 Td {body} ET"
    ).encode("cp1252")


def build_pdf(pages: dict[int, list[str]], page_count: int) -> bytes:
    """A PDF of `page_count` pages; `pages` maps a page number to its [title, text]."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # the page tree, once the page ids are known
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
        b" /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold"
        b" /Encoding /WinAnsiEncoding >>",
    ]
    page_ids: list[int] = []
    for number in range(1, page_count + 1):
        title, text = pages.get(number, ["", ""])
        stream = _page_stream(title, text) if title else b""
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            b"" + stream + b"\nendstream"
        )
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                f"/Contents {len(objects)} 0 R >>"
            ).encode()
        )
        page_ids.append(len(objects))
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode()

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()
