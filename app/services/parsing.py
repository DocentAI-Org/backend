"""Text extraction from uploaded material (T2, research R10)."""

import io
import re
from dataclasses import dataclass
from pathlib import PurePath

EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "markdown",
    ".markdown": "markdown",
}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "markdown": "text/markdown",
}
PREFACE_SECTION = "Inicio"
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


class ParsingError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Section:
    section: str
    location_label: str
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    sections: list[Section]
    page_count: int


def detect_file_type(file_name: str) -> str | None:
    return EXTENSIONS.get(PurePath(file_name).suffix.lower())


def parse_document(file_type: str, content: bytes) -> ParsedDocument:
    if file_type == "pdf":
        parsed = _parse_pdf(content)
    elif file_type == "docx":
        parsed = _parse_docx(content)
    elif file_type == "markdown":
        parsed = _parse_markdown(content)
    else:
        raise ParsingError("unsupported_format")
    if not any(section.text.strip() for section in parsed.sections):
        raise ParsingError("no_readable_text")
    return parsed


def _parse_pdf(content: bytes) -> ParsedDocument:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PyPdfError, ValueError, OSError) as exc:
        raise ParsingError("unsupported_format") from exc
    sections = [
        Section(str(number), f"p. {number}", text.strip())
        for number, text in enumerate(pages, start=1)
        if text.strip()
    ]
    return ParsedDocument(sections=sections, page_count=len(pages))


def _by_headings(blocks: list[tuple[str | None, str]]) -> ParsedDocument:
    """`blocks` are (heading, None) or (None, paragraph) in document order."""
    sections: list[Section] = []
    current = PREFACE_SECTION
    paragraphs: list[str] = []

    def close() -> None:
        text = "\n\n".join(p for p in paragraphs if p.strip()).strip()
        if text:
            sections.append(Section(current, f"§ {current}", text))

    for heading, paragraph in blocks:
        if heading is not None:
            close()
            current, paragraphs = heading, []
        else:
            paragraphs.append(paragraph)
    close()
    return ParsedDocument(sections=sections, page_count=len(sections))


def _parse_docx(content: bytes) -> ParsedDocument:
    from docx import Document

    try:
        document = Document(io.BytesIO(content))
    except Exception as exc:  # BadZipFile, PackageNotFoundError, lxml errors...
        raise ParsingError("unsupported_format") from exc
    blocks: list[tuple[str | None, str]] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        if style.startswith(("Heading", "Título", "Title")):
            blocks.append((text, ""))
        else:
            blocks.append((None, text))
    return _by_headings(blocks)


def _parse_markdown(content: bytes) -> ParsedDocument:
    text = content.decode("utf-8", errors="replace")
    blocks: list[tuple[str | None, str]] = []
    paragraph: list[str] = []
    in_code = False

    def flush() -> None:
        if paragraph:
            blocks.append((None, " ".join(line.strip() for line in paragraph)))
            paragraph.clear()

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        heading = None if in_code else _MD_HEADING.match(line)
        if heading:
            flush()
            blocks.append((heading.group(1).strip(), ""))
        elif not line.strip():
            flush()
        else:
            paragraph.append(line)
    flush()
    return _by_headings(blocks)
