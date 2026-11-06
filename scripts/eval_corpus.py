"""Fetches the evaluation material that is not kept in git (specs/017 US1).

Downloads each subject's source PDF, checks it against the pinned SHA-256 and keeps only
the chapter pages, in `tests/eval/corpus/.cache/`. Run once per clone:

    uv run python scripts/eval_corpus.py
"""

import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

from pypdf import PdfReader, PdfWriter

CORPUS = Path(__file__).resolve().parent.parent / "tests" / "eval" / "corpus"
CACHE = CORPUS / ".cache"


def fetch(subject: Path) -> str:
    material = json.loads(subject.read_text())["material"]
    source = material.get("source")
    target = CACHE / material["file"]
    if source is None:
        return "in git"
    if target.exists():
        return "cached"
    with urllib.request.urlopen(source["url"], timeout=300) as response:
        content = response.read()
    digest = hashlib.sha256(content).hexdigest()
    if digest != source["sha256"]:
        raise SystemExit(
            f"{subject.parent.name}: the source changed (SHA-256 {digest}); check "
            "the pages in subject.json against the new edition, then update the hash."
        )
    first, last = source["pages"]
    reader = PdfReader(io.BytesIO(content))
    writer = PdfWriter()
    for number in range(first, last + 1):
        writer.add_page(reader.pages[number - 1])
    CACHE.mkdir(exist_ok=True)
    with target.open("wb") as out:
        writer.write(out)
    return f"fetched, pages {first}-{last}"


def main() -> None:
    for subject in sorted(CORPUS.glob("*/subject.json")):
        print(f"{subject.parent.name}: {fetch(subject)}")


if __name__ == "__main__":
    sys.exit(main())
