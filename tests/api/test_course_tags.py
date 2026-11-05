"""Spec 016 US4 — each user's own tags on their courses."""

from tests.api.test_list_tools import join, names
from tests.api.test_us2_courses import create_course

TAGS = "/v1/me/course-tags"


def new_tag(client, user, name: str = "1er trimestre", color: str = "violet"):
    return client.post(TAGS, headers=user.headers, json={"name": name, "color": color})


def tag_course(client, user, tag_id: str, course_id: str):
    return client.put(f"{TAGS}/{tag_id}/courses/{course_id}", headers=user.headers)


def untag_course(client, user, tag_id: str, course_id: str):
    return client.delete(f"{TAGS}/{tag_id}/courses/{course_id}", headers=user.headers)


def my_tags(client, user) -> list[dict]:
    response = client.get(TAGS, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_tag_is_listed_with_its_count(client, teacher) -> None:
    created = new_tag(client, teacher, "Repaso", "green")

    assert created.status_code == 201, created.text
    tag = created.json()
    assert tag == {
        "id": tag["id"],
        "name": "Repaso",
        "color": "green",
        "course_count": 0,
    }
    assert my_tags(client, teacher) == [tag]


def test_tags_go_on_courses_and_filter_the_list(client, teacher) -> None:
    algebra = create_course(client, teacher, "Álgebra")
    create_course(client, teacher, "Historia")
    review = new_tag(client, teacher, "Repaso", "amber").json()
    term = new_tag(client, teacher, "1er trimestre").json()

    assert tag_course(client, teacher, review["id"], algebra["id"]).status_code == 204
    assert tag_course(client, teacher, term["id"], algebra["id"]).status_code == 204
    assert tag_course(client, teacher, term["id"], algebra["id"]).status_code == 204

    listed = client.get("/v1/teacher/courses", headers=teacher.headers).json()
    tagged = next(c for c in listed["items"] if c["id"] == algebra["id"])
    only = client.get(
        f"/v1/teacher/courses?tag={review['id']}", headers=teacher.headers
    )

    assert [t["name"] for t in tagged["tags"]] == ["1er trimestre", "Repaso"]
    assert tagged["tags"][1] == {"id": review["id"], "name": "Repaso", "color": "amber"}
    assert names(only) == ["Álgebra"]
    assert {t["name"]: t["course_count"] for t in my_tags(client, teacher)} == {
        "1er trimestre": 1,
        "Repaso": 1,
    }

    assert untag_course(client, teacher, review["id"], algebra["id"]).status_code == 204
    assert untag_course(client, teacher, review["id"], algebra["id"]).status_code == 204
    after = client.get(
        f"/v1/teacher/courses?tag={review['id']}", headers=teacher.headers
    )
    assert names(after) == []


def test_students_tag_the_courses_they_are_in(client, teacher, student) -> None:
    course = create_course(client, teacher, "Álgebra")
    join(client, student, course)
    tag = new_tag(client, student, "Difícil", "red").json()

    assert tag_course(client, student, tag["id"], course["id"]).status_code == 204
    mine = client.get(f"/v1/student/courses?tag={tag['id']}", headers=student.headers)
    teachers = client.get("/v1/teacher/courses", headers=teacher.headers).json()

    assert names(mine) == ["Álgebra"]
    assert mine.json()["items"][0]["tags"][0]["name"] == "Difícil"
    assert teachers["items"][0]["tags"] == []


def test_renaming_recolouring_and_deleting(client, teacher) -> None:
    course = create_course(client, teacher)
    tag = new_tag(client, teacher).json()
    tag_course(client, teacher, tag["id"], course["id"])

    renamed = client.patch(
        f"{TAGS}/{tag['id']}",
        headers=teacher.headers,
        json={"name": "2º trimestre", "color": "blue"},
    )
    shown = client.get("/v1/teacher/courses", headers=teacher.headers).json()

    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "2º trimestre"
    assert shown["items"][0]["tags"][0]["color"] == "blue"

    assert (
        client.delete(f"{TAGS}/{tag['id']}", headers=teacher.headers).status_code == 204
    )
    assert my_tags(client, teacher) == []
    after = client.get("/v1/teacher/courses", headers=teacher.headers).json()
    assert after["total"] == 1
    assert after["items"][0]["tags"] == []


def test_names_and_colours_are_validated(client, teacher) -> None:
    new_tag(client, teacher, "Repaso")

    taken = new_tag(client, teacher, "repaso", "green")
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "tag_name_taken"
    for name, color in (
        ("", "green"),
        ("   ", "green"),
        ("x" * 41, "green"),
        ("Otra", "pink"),
    ):
        assert new_tag(client, teacher, name, color).status_code == 422, (name, color)
    other = new_tag(client, teacher, "Otra").json()
    clash = client.patch(
        f"{TAGS}/{other['id']}", headers=teacher.headers, json={"name": "REPASO"}
    )
    assert clash.status_code == 409


def test_tags_are_private_and_courses_must_be_yours(
    client, teacher, other_teacher, student
) -> None:
    mine = new_tag(client, teacher).json()
    theirs_course = create_course(client, other_teacher)

    assert my_tags(client, other_teacher) == []
    assert (
        tag_course(client, teacher, mine["id"], theirs_course["id"]).status_code == 404
    )
    other_tag = new_tag(client, other_teacher).json()
    own_course = create_course(client, teacher)
    assert (
        tag_course(client, teacher, other_tag["id"], own_course["id"]).status_code
        == 404
    )
    for call in (
        client.patch(
            f"{TAGS}/{other_tag['id']}", headers=teacher.headers, json={"name": "Mía"}
        ),
        client.delete(f"{TAGS}/{other_tag['id']}", headers=teacher.headers),
    ):
        assert call.status_code == 404
    assert tag_course(client, student, mine["id"], own_course["id"]).status_code == 404


def test_admins_have_no_tags(client, admin) -> None:
    assert client.get(TAGS, headers=admin.headers).status_code == 403
    assert new_tag(client, admin).status_code == 403


def test_a_removed_student_no_longer_counts_the_course(
    client, teacher, student
) -> None:
    course = create_course(client, teacher)
    join(client, student, course)
    tag = new_tag(client, student).json()
    tag_course(client, student, tag["id"], course["id"])

    client.delete(
        f"/v1/teacher/courses/{course['id']}/students/{student.id}",
        headers=teacher.headers,
    )

    assert my_tags(client, student)[0]["course_count"] == 0
