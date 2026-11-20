"""Builds small PDF and DOCX files in memory, so tests need no binary fixtures."""

import io

from docx import Document as DocxDocument
from pypdf import PdfReader, PdfWriter

Line = tuple[float, str]


def build_pdf(
    pages: list[str] | list[list[Line]], outline: list[tuple[str, int]] = ()
) -> bytes:
    """A minimal valid PDF in Helvetica: one 12 pt line per page, or a page's lines as
    (size, text) from the top; `outline` adds bookmarks (title, page index)."""
    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, text in enumerate(pages):
        content_id = page_ids[index] + 1
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        lines = [(12.0, text)] if isinstance(text, str) else text
        stream = " ".join(
            f"BT /F1 {size} Tf 72 {720 - 24 * row} Td ({_escape(line)}) Tj ET"
            for row, (size, line) in enumerate(lines)
        ).encode("latin-1")
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

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
    if not outline:
        return out.getvalue()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(out.getvalue())))
    for title, page in outline:
        writer.add_outline_item(title=title, page_number=page)
    with_outline = io.BytesIO()
    writer.write(with_outline)
    return with_outline.getvalue()


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_docx(blocks: list[tuple[str, str]]) -> bytes:
    """`blocks` are (style, text) pairs, e.g. ("Heading 1", "Tema") or ("", "texto")."""
    document = DocxDocument()
    for style, text in blocks:
        if style.startswith("Heading"):
            document.add_heading(text, level=int(style.split()[-1]))
        else:
            document.add_paragraph(text)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()
