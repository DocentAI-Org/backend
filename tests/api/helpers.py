"""Shared setup for stories that need an enrolled student and validated material."""

from dataclasses import dataclass

from tests.api.test_us2_courses import create_course
from tests.api.test_us3_material import validated_document


@dataclass
class Classroom:
    course: dict
    document: dict

    @property
    def course_id(self) -> str:
        return self.course["id"]


def classroom(client, teacher, student, acknowledge: bool = True) -> Classroom:
    course = create_course(client, teacher)
    document = validated_document(client, teacher, course["id"])
    client.post(
        "/v1/student/enrolments",
        headers=student.headers,
        json={"class_code": course["class_code"]},
    )
    if acknowledge:
        client.post(
            f"/v1/student/courses/{course['id']}/disclosure", headers=student.headers
        )
    return Classroom(course=course, document=document)


def open_conversation(client, student, course_id: str) -> dict:
    response = client.post(
        f"/v1/student/courses/{course_id}/conversations", headers=student.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def ask(
    client,
    student,
    course_id: str,
    conversation_id: str,
    text: str,
    request_solution: bool = False,
):
    return client.post(
        f"/v1/student/courses/{course_id}/conversations/{conversation_id}/messages",
        headers=student.headers,
        json={"text": text, "request_solution": request_solution},
    )


COVERED_QUESTION = "¿Cómo despejo la incógnita en 2x = 4 si está multiplicada?"
UNCOVERED_QUESTION = "¿Quién ganó el mundial de fútbol de 2010?"
