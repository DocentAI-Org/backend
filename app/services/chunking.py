"""Splits sections into retrievable fragments (research R10).

Paragraphs are merged up to `max_chars`; fragments never cross a section, so each
one keeps a single page or section reference for citations.
"""

import re
from dataclasses import dataclass

from app.services.parsing import Section

DEFAULT_MAX_CHARS = 1200
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class Chunk:
    section: str
    location_label: str
    text: str


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(paragraph):
        while len(sentence) > max_chars:
            pieces.extend([current] if current else [])
            current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return [p for p in pieces if p.strip()]


def chunk_sections(
    sections: list[Section], max_chars: int = DEFAULT_MAX_CHARS
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        paragraphs: list[str] = []
        for paragraph in re.split(r"\n\s*\n", section.text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(paragraph) > max_chars:
                paragraphs.extend(_split_long(paragraph, max_chars))
            else:
                paragraphs.append(paragraph)

        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if len(candidate) <= max_chars:
                current = candidate
                continue
            chunks.append(Chunk(section.section, section.location_label, current))
            current = paragraph
        if current:
            chunks.append(Chunk(section.section, section.location_label, current))
    return chunks
