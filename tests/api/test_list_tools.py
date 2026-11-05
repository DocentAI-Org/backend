"""Spec 016 — search, sort and favourites in the lists."""

import pytest

from app.models import Profile
from tests.api.helpers import (
    COVERED_QUESTION,
    UNCOVERED_QUESTION,
    ask,
    classroom,
    give_consent,
    open_conversation,
)
from tests.api.test_quiz_questions import generated, questions_path
from tests.api.test_us2_courses import create_course
from tests.api.test_us3_material import MARKDOWN, upload


def names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def join(client, student, course: dict) -> None:
    response = client.post(
        "/v1/student/enrolments",
        headers=student.headers,
        json={"class_code": course["class_code"]},
    )
    assert response.status_code in (200, 201), response.text


def star(client, user, course_id: str):
    return client.put(f"/v1/me/favorite-courses/{course_id}", headers=user.headers)


def unstar(client, user, course_id: str):
    return client.delete(f"/v1/me/favorite-courses/{course_id}", headers=user.headers)


# --- US1 search -----------------------------------------------------------------


def test_course_search_ignores_case_and_accents(client, teacher) -> None:
    create_course(client, teacher, "Álgebra 3º")
    create_course(client, teacher, "Geometría")

    found = client.get("/v1/teacher/courses?q=ALGEBRA", headers=teacher.headers)

    assert names(found) == ["Álgebra 3º"]
    assert found.json()["total"] == 1


def test_every_word_must_match_some_field(client, teacher, student) -> None:
    course = create_course(client, teacher, "Álgebra")
    create_course(client, teacher, "Geometría")
    join(client, student, course)

    # "ruiz" is the teacher's name, "algebra" the course's; each must match a field.
    both = client.get("/v1/student/courses?q=ruiz algebra", headers=student.headers)
    neither = client.get("/v1/student/courses?q=ruiz historia", headers=student.headers)

    assert names(both) == ["Álgebra"]
    assert names(neither) == []


def test_blank_search_is_no_search(client, teacher) -> None:
    create_course(client, teacher, "Uno")
    create_course(client, teacher, "Dos")

    everything = client.get("/v1/teacher/courses?q=%20%20", headers=teacher.headers)

    assert everything.json()["total"] == 2


def test_students_are_found_by_name(client, teacher, make_user) -> None:
    course = create_course(client, teacher)
    for name in ("Ana García", "Luis Pérez", "Ana Martín"):
        join(client, make_user("student", name), course)
    path = f"/v1/teacher/courses/{course['id']}/students"

    found = client.get(f"{path}?q=garcia ana", headers=teacher.headers).json()

    assert [s["display_name"] for s in found["items"]] == ["Ana García"]
    assert found["total"] == 1


def test_conversations_are_found_by_message_text_and_keep_filters(
    client, teacher, student, other_student
) -> None:
    room = classroom(client, teacher, student)
    mine = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, mine["id"], COVERED_QUESTION)
    join(client, other_student, room.course)
    give_consent(client, other_student)
    client.post(
        f"/v1/student/courses/{room.course_id}/disclosure",
        headers=other_student.headers,
    )
    theirs = open_conversation(client, other_student, room.course_id)
    ask(client, other_student, room.course_id, theirs["id"], UNCOVERED_QUESTION)
    base = f"/v1/teacher/courses/{room.course_id}/conversations"

    by_text = client.get(f"{base}?q=futbol", headers=teacher.headers).json()
    by_name = client.get(f"{base}?q=herrera", headers=teacher.headers).json()
    filtered = client.get(
        f"{base}?q=futbol&student_id={student.id}", headers=teacher.headers
    ).json()

    assert [c["id"] for c in by_text["items"]] == [theirs["id"]]
    assert [c["id"] for c in by_name["items"]] == [mine["id"]]
    assert filtered["total"] == 0


def test_documents_are_found_by_file_name(client, teacher) -> None:
    course = create_course(client, teacher)
    for name in ("ecuaciones.md", "geometría.md"):
        assert upload(client, teacher, course["id"], name, MARKDOWN).status_code == 202
    path = f"/v1/teacher/courses/{course['id']}/documents"

    found = client.get(f"{path}?q=geometria", headers=teacher.headers).json()

    assert [d["file_name"] for d in found["items"]] == ["geometría.md"]


def test_questions_are_found_by_statement_or_topic_and_counts_follow(
    client, llm, teacher, student
) -> None:
    room, _, made = generated(client, llm, teacher, student)
    path = questions_path(room.course_id)

    by_statement = client.get(f"{path}?q=cuanto vale", headers=teacher.headers).json()
    by_topic = client.get(f"{path}?q=parentesis", headers=teacher.headers).json()

    assert [q["id"] for q in by_statement["items"]] == [made[0]["id"]]
    assert by_statement["counts"] == {"pending": 1, "approved": 0, "rejected": 0}
    assert by_topic["total"] == 3


def test_admin_finds_users_by_email_and_keeps_filters(
    client, db, admin, teacher, student
) -> None:
    email = db.get(Profile, student.id).email
    part = email.split("@")[0][2:8]

    found = client.get(f"/v1/admin/users?q={part}", headers=admin.headers).json()
    as_teacher = client.get(
        f"/v1/admin/users?q={part}&role=teacher", headers=admin.headers
    ).json()

    assert [u["id"] for u in found["items"]] == [str(student.id)]
    assert as_teacher["total"] == 0


def test_admin_finds_courses_by_teacher_name(
    client, admin, teacher, other_teacher
) -> None:
    create_course(client, teacher, "Álgebra")
    create_course(client, other_teacher, "Historia")

    found = client.get("/v1/admin/courses?q=ruiz", headers=admin.headers)

    assert names(found) == ["Álgebra"]


# --- US2 sort -------------------------------------------------------------------


def test_sort_by_name_and_default_order(client, teacher) -> None:
    for name in ("B", "a", "C"):
        create_course(client, teacher, name)

    by_name = client.get("/v1/teacher/courses?sort=name", headers=teacher.headers)
    recent = client.get("/v1/teacher/courses?sort=recent", headers=teacher.headers)
    default = client.get("/v1/teacher/courses", headers=teacher.headers)

    assert names(by_name) == ["a", "B", "C"]
    assert names(recent) == ["C", "a", "B"]
    assert names(default) == names(recent)


@pytest.mark.parametrize(
    "path",
    [
        "/v1/teacher/courses",
        "/v1/student/courses",
        "/v1/admin/users",
        "/v1/admin/courses",
    ],
)
def test_unknown_sort_is_rejected(client, admin, teacher, student, path) -> None:
    user = {"teacher": teacher, "student": student, "admin": admin}[path.split("/")[2]]

    response = client.get(f"{path}?sort=sideways", headers=user.headers)

    assert response.status_code == 422


def test_students_sort_by_name(client, teacher, make_user) -> None:
    course = create_course(client, teacher)
    for name in ("Zoe", "ana"):
        join(client, make_user("student", name), course)
    path = f"/v1/teacher/courses/{course['id']}/students"

    joined = client.get(path, headers=teacher.headers).json()
    by_name = client.get(f"{path}?sort=name", headers=teacher.headers).json()

    assert [s["display_name"] for s in joined["items"]] == ["Zoe", "ana"]
    assert [s["display_name"] for s in by_name["items"]] == ["ana", "Zoe"]


def test_conversations_sort_oldest_first(client, teacher, student) -> None:
    room = classroom(client, teacher, student)
    first = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, first["id"], COVERED_QUESTION)
    second = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, second["id"], COVERED_QUESTION)
    base = f"/v1/teacher/courses/{room.course_id}/conversations"

    oldest = client.get(f"{base}?sort=oldest", headers=teacher.headers).json()

    assert [c["id"] for c in oldest["items"]] == [first["id"], second["id"]]


# --- US3 favourites --------------------------------------------------------------


def test_a_starred_course_comes_first_until_unstarred(client, teacher) -> None:
    oldest = create_course(client, teacher, "Primero")
    create_course(client, teacher, "Segundo")
    create_course(client, teacher, "Tercero")

    assert star(client, teacher, oldest["id"]).status_code == 204
    starred = client.get("/v1/teacher/courses", headers=teacher.headers).json()
    by_name = client.get("/v1/teacher/courses?sort=name", headers=teacher.headers)

    assert [c["name"] for c in starred["items"]] == ["Primero", "Tercero", "Segundo"]
    assert [c["is_favorite"] for c in starred["items"]] == [True, False, False]
    assert names(by_name) == ["Primero", "Segundo", "Tercero"]

    assert unstar(client, teacher, oldest["id"]).status_code == 204
    after = client.get("/v1/teacher/courses", headers=teacher.headers)
    assert names(after) == ["Tercero", "Segundo", "Primero"]


def test_starring_twice_and_unstarring_twice_are_not_errors(client, teacher) -> None:
    course = create_course(client, teacher)

    assert star(client, teacher, course["id"]).status_code == 204
    assert star(client, teacher, course["id"]).status_code == 204
    assert unstar(client, teacher, course["id"]).status_code == 204
    assert unstar(client, teacher, course["id"]).status_code == 204


def test_students_star_the_courses_they_are_in(client, teacher, student) -> None:
    first = create_course(client, teacher, "Primero")
    second = create_course(client, teacher, "Segundo")
    join(client, student, first)
    join(client, student, second)

    assert star(client, student, first["id"]).status_code == 204
    listed = client.get("/v1/student/courses", headers=student.headers).json()

    assert [c["name"] for c in listed["items"]] == ["Primero", "Segundo"]
    assert [c["is_favorite"] for c in listed["items"]] == [True, False]


def test_only_your_own_courses_can_be_starred(
    client, teacher, other_teacher, student
) -> None:
    theirs = create_course(client, other_teacher)

    assert star(client, teacher, theirs["id"]).status_code == 404
    assert star(client, student, theirs["id"]).status_code == 404
    unknown = "00000000-0000-0000-0000-000000000000"
    assert star(client, teacher, unknown).status_code == 404


def test_favourites_are_per_user(client, teacher, student, other_student) -> None:
    course = create_course(client, teacher)
    join(client, student, course)
    join(client, other_student, course)

    star(client, student, course["id"])
    theirs = client.get("/v1/student/courses", headers=other_student.headers).json()
    teachers = client.get("/v1/teacher/courses", headers=teacher.headers).json()

    assert theirs["items"][0]["is_favorite"] is False
    assert teachers["items"][0]["is_favorite"] is False


def test_a_removed_student_loses_the_course_and_its_star(
    client, teacher, student
) -> None:
    course = create_course(client, teacher)
    join(client, student, course)
    star(client, student, course["id"])

    client.delete(
        f"/v1/teacher/courses/{course['id']}/students/{student.id}",
        headers=teacher.headers,
    )
    listed = client.get("/v1/student/courses", headers=student.headers).json()

    assert listed["total"] == 0
    assert star(client, student, course["id"]).status_code == 404


def test_admins_have_no_favourites(client, admin, teacher) -> None:
    course = create_course(client, teacher)

    assert star(client, admin, course["id"]).status_code == 403
