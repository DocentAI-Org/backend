"""The evaluation corpus (specs/017 US1): one folder per subject under `corpus/`.

`subject.json` names the material, the topics and the cases of each task. The material
is next to it (Markdown, or Markdown that becomes DOCX here), in `tests/fixtures`, or
fetched by `scripts/eval_corpus.py` into `corpus/.cache/` (a PDF cut to its chapter).
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.models import Fragment
from tests.api.helpers import give_consent
from tests.api.test_us2_courses import create_course
from tests.api.test_us3_material import upload
from tests.api.test_us6_topics import create_topic
from tests.builders import build_docx

CORPUS = Path(__file__).parent / "corpus"
CACHE = CORPUS / ".cache"
FIXTURES = Path(__file__).parent.parent / "fixtures"


def markdown_to_docx(text: str) -> bytes:
    """Headings become DOCX headings, every other paragraph or list item a paragraph."""
    blocks: list[tuple[str, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(("", " ".join(paragraph)))
            paragraph.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            level = len(stripped) - len(stripped.lstrip("#"))
            blocks.append((f"Heading {level}", stripped.lstrip("#").strip()))
        elif not stripped or stripped.startswith("- "):
            flush()
            if stripped:
                paragraph.append(stripped[2:])
        else:
            paragraph.append(stripped)
    flush()
    return build_docx(blocks)


@dataclass(frozen=True)
class Subject:
    slug: str
    data: dict

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def file_name(self) -> str:
        return self.data["material"]["file"]

    def material(self) -> bytes | None:
        """The file to upload; None when it has not been fetched yet."""
        material = self.data["material"]
        if "source" in material:
            path = CACHE / material["file"]
            return path.read_bytes() if path.exists() else None
        if "from_markdown" in material:
            return markdown_to_docx(
                (CORPUS / self.slug / material["from_markdown"]).read_text()
            )
        folder = FIXTURES if material.get("fixture") else CORPUS / self.slug
        return (folder / material["file"]).read_bytes()

    def topic_sections(self) -> dict[str, list[str]]:
        """Each topic's sections as the parser names them: headings, or the page of the
        cut PDF (page 1 is the first page kept)."""
        first = self.data["material"].get("source", {}).get("pages", [1])[0]
        sections = {}
        for topic in self.data["topics"]:
            if "pages" in topic:
                start, end = topic["pages"]
                sections[topic["name"]] = [
                    str(p - first + 1) for p in range(start, end + 1)
                ]
            else:
                sections[topic["name"]] = topic["sections"]
        return sections


def subjects() -> list[Subject]:
    """All subjects, or those in EVAL_SUBJECTS (comma-separated folder names)."""
    wanted = {s for s in os.environ.get("EVAL_SUBJECTS", "").split(",") if s}
    return [
        Subject(path.parent.name, json.loads(path.read_text()))
        for path in sorted(CORPUS.glob("*/subject.json"))
        if not wanted or path.parent.name in wanted
    ]


@dataclass
class Room:
    """A course with the subject's material validated and its topics assigned."""

    subject: Subject
    course: dict
    document_id: str
    topic_ids: dict[str, str]
    sections: dict[str, list[str]] = field(default_factory=dict)

    @property
    def course_id(self) -> str:
        return self.course["id"]

    def topics_of(self, section: str) -> set[str]:
        return {name for name, sections in self.sections.items() if section in sections}


def open_room(client, db, teacher, subject: Subject, content: bytes) -> Room:
    course = create_course(client, teacher)
    response = upload(client, teacher, course["id"], subject.file_name, content)
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]
    base = f"/v1/teacher/courses/{course['id']}/documents/{document_id}"
    document = client.get(base, headers=teacher.headers).json()
    assert document["processing_status"] == "ready", document
    response = client.post(f"{base}/validate", headers=teacher.headers)
    assert response.status_code == 200, response.text

    present = set(
        db.scalars(select(Fragment.section).where(Fragment.document_id == document_id))
    )
    room = Room(subject, course, document_id, {}, subject.topic_sections())
    for name, sections in room.sections.items():
        topic = create_topic(client, teacher, course["id"], name).json()
        room.topic_ids[name] = topic["id"]
        found = [s for s in sections if s in present]
        assert found, f"{subject.slug}: no fragment in the sections of {name!r}"
        for section in found:
            response = client.post(
                f"/v1/teacher/courses/{course['id']}/topic-assignments",
                headers=teacher.headers,
                json={
                    "topic_id": topic["id"],
                    "document_id": document_id,
                    "section": section,
                },
            )
            assert response.status_code == 201, response.text
    return room


def enrolled_student(client, make_user, room: Room):
    """A new student in the room, with consent and the AI disclosure acknowledged."""
    student = make_user("student")
    client.post(
        "/v1/student/enrolments",
        headers=student.headers,
        json={"class_code": room.course["class_code"]},
    )
    give_consent(client, student)
    client.post(
        f"/v1/student/courses/{room.course_id}/disclosure", headers=student.headers
    )
    return student
