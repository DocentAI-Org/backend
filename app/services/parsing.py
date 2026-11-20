"""Text extraction from uploaded material (T2, research R10)."""

import io
import re
from collections import Counter
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
    # Postgres text cannot hold NUL, which PDF extraction sometimes produces.
    sections = [
        Section(s.section, s.location_label, s.text.replace("\x00", ""))
        for s in parsed.sections
    ]
    parsed = ParsedDocument(sections=sections, page_count=parsed.page_count)
    if not any(section.text.strip() for section in parsed.sections):
        raise ParsingError("no_readable_text")
    return parsed


def _parse_pdf(content: bytes) -> ParsedDocument:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [_page_lines(page) for page in reader.pages]
        outline = _outline(reader)
    except (PyPdfError, ValueError, OSError) as exc:
        raise ParsingError("unsupported_format") from exc
    # The document's own sections (specs/024): its outline, else its headings by type
    # size, else its pages.
    starts = _outline_starts(pages, outline) or _heading_starts(pages)
    if not starts:
        sections = [
            Section(str(number), f"p. {number}", text)
            for number, lines in enumerate(pages, start=1)
            if (text := "\n".join(line.text for line in lines).strip())
        ]
    else:
        sections = _sections_from_starts(pages, starts)
    return ParsedDocument(sections=sections, page_count=len(pages))


@dataclass(frozen=True)
class _Line:
    text: str
    size: float


# Spans closer than this (in points) vertically are on the same line.
_SAME_LINE = 1.0
# A heading is set at least this much larger than the body text.
_HEADING_RATIO = 1.2
# Text repeated on more pages than this is a running header or footer.
_RUNNING_PAGES = 2


def _page_lines(page) -> list[_Line]:
    """The page's text by line, each with the size most of its characters are set in."""
    lines: list[tuple[float | None, list[tuple[str, float]]]] = []

    def visit(text, cm, tm, _font, font_size) -> None:
        if not text:
            return
        y = tm[5] * cm[3] + cm[5] if tm and cm else None
        size = round(abs(font_size * tm[3] * cm[3]), 1) if tm and cm else font_size
        if "\n" in text or not lines or _apart(lines[-1][0], y):
            lines.append((y, []))
        lines[-1][1].append((text.replace("\n", " "), size))

    page.extract_text(visitor_text=visit)
    result = []
    for _, spans in lines:
        text = " ".join("".join(t for t, _ in spans).split())
        if text:
            sizes = Counter[float]()
            for t, size in spans:
                sizes[size] += len(t.strip())
            result.append(_Line(text, sizes.most_common(1)[0][0]))
    return result


def _apart(y: float | None, other: float | None) -> bool:
    return y is None or other is None or abs(y - other) > _SAME_LINE


def _outline(reader) -> list[tuple[str, int]]:
    """Top-level bookmarks (title, page index), or the next level under a single one."""
    entries = list(reader.outline)
    top = [e for e in entries if not isinstance(e, list)]
    if len(top) == 1:
        children = next((e for e in entries if isinstance(e, list)), [])
        top = [e for e in children if not isinstance(e, list)] or top
    result = []
    for entry in top:
        page = reader.get_destination_page_number(entry)
        if entry.title and page is not None and page >= 0:
            result.append((str(entry.title).strip(), page))
    return result


def _normal(text: str) -> str:
    return " ".join(text.lower().split())


def _outline_starts(
    pages: list[list[_Line]], outline: list[tuple[str, int]]
) -> list[tuple[int, int, str]]:
    """(page, line, title) where each bookmark starts: its title's line on its page, or
    the top of the page."""
    starts = []
    for title, page in outline:
        if page >= len(pages):
            continue
        wanted = _normal(title)
        line = next(
            (
                index
                for index, candidate in enumerate(pages[page])
                if _normal(candidate.text).startswith(wanted)
            ),
            0,
        )
        starts.append((page, line, title))
    return sorted(starts)


def _heading_starts(pages: list[list[_Line]]) -> list[tuple[int, int, str]]:
    """(page, line, heading) for the largest type size above the body that marks at
    least two headings; a heading over consecutive lines is one."""
    chars = Counter[float]()
    for lines in pages:
        for line in lines:
            chars[line.size] += len(line.text)
    if not chars:
        return []
    body = chars.most_common(1)[0][0]
    for size in sorted((s for s in chars if s >= body * _HEADING_RATIO), reverse=True):
        headings = _headings_of_size(pages, size)
        if len(headings) >= 2:
            return headings
    return []


def _headings_of_size(
    pages: list[list[_Line]], size: float
) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for page, lines in enumerate(pages):
        index = 0
        while index < len(lines):
            if lines[index].size != size:
                index += 1
                continue
            first = index
            while index < len(lines) and lines[index].size == size:
                index += 1
            text = " ".join(line.text for line in lines[first:index])
            if any(c.isalpha() for c in text) and len(text) <= 200:
                found.append((page, first, text))
    repeated = Counter(_without_digits(text) for _, _, text in found)
    return [h for h in found if repeated[_without_digits(h[2])] <= _RUNNING_PAGES]


def _without_digits(text: str) -> str:
    return _normal(re.sub(r"\d+", "", text))


def _sections_from_starts(
    pages: list[list[_Line]], starts: list[tuple[int, int, str]]
) -> list[Section]:
    """One section per heading, cut by page so each piece keeps its page for citations.
    Text before the first heading is the preface; repeated headings are numbered."""
    names = _unique([title for _, _, title in starts])
    at = {
        (page, line): name for (page, line, _), name in zip(starts, names, strict=True)
    }
    pieces: list[tuple[str, int, list[str]]] = []
    current = PREFACE_SECTION
    for page, lines in enumerate(pages):
        pieces.append((current, page, []))
        for index, line in enumerate(lines):
            if (page, index) in at:
                current = at[(page, index)]
                pieces.append((current, page, []))
            pieces[-1][2].append(line.text)
    return [
        Section(name, f"§ {name}, p. {page + 1}", text)
        for name, page, lines in pieces
        if (text := "\n".join(lines).strip())
    ]


def _unique(names: list[str]) -> list[str]:
    seen = Counter[str]()
    result = []
    for name in names:
        seen[name] += 1
        result.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return result


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
    text = content.decode("utf-8", errors="replace").replace("\x00", "")
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
