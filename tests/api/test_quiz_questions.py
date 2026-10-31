"""US1–US2 (spec 006) — the teacher drafts quiz questions with the AI, reviews them."""

from sqlalchemy import select

from app.models import InteractionLog
from tests.api.helpers import classroom
from tests.api.test_us2_courses import create_course
from tests.api.test_us6_topics import create_topic

SECTION = "3.3 Quitar paréntesis"


def draft(statement: str, correct: str = "B", difficulty=1, cited=None) -> dict:
    return {
        "statement": statement,
        "options": ["2x - 3", "2x - 6", "2x + 6", "x - 6"],
        "correct": correct,
        "explanation": "El 2 multiplica a cada término de dentro (F1).",
        "difficulty": difficulty,
        "cited": cited or ["F1"],
    }


DRAFTS = {
    "questions": [
        draft("¿Cuánto vale 2(x - 3) sin paréntesis?"),
        draft("Al quitar el paréntesis en 2(x - 3), ¿qué queda?", difficulty=2),
        draft("¿Qué expresión es igual a 2(x - 3)?", difficulty=3),
    ]
}


def topic_with_material(client, teacher, course_id: str, document_id: str) -> dict:
    topic = create_topic(client, teacher, course_id, "Paréntesis").json()
    response = client.post(
        f"/v1/teacher/courses/{course_id}/topic-assignments",
        headers=teacher.headers,
        json={"topic_id": topic["id"], "document_id": document_id, "section": SECTION},
    )
    assert response.status_code == 201, response.text
    return topic


def generate(client, teacher, course_id: str, topic_id: str, count: int | None = 3):
    return client.post(
        f"/v1/teacher/courses/{course_id}/topics/{topic_id}/questions/generate",
        headers=teacher.headers,
        json={} if count is None else {"count": count},
    )


def questions_path(course_id: str) -> str:
    return f"/v1/teacher/courses/{course_id}/questions"


def edit(client, teacher, course_id: str, question_id: str, **changes):
    return client.patch(
        f"{questions_path(course_id)}/{question_id}",
        headers=teacher.headers,
        json=changes,
    )


def generated(client, llm, teacher, student, replies=DRAFTS):
    room = classroom(client, teacher, student)
    topic = topic_with_material(client, teacher, room.course_id, room.document["id"])
    llm.reply = replies
    response = generate(client, teacher, room.course_id, topic["id"], count=10)
    assert response.status_code == 201, response.text
    return room, topic, response.json()["questions"]


def approved_questions(client, llm, teacher, student, replies=DRAFTS):
    room, topic, made = generated(client, llm, teacher, student, replies)
    for question in made:
        response = edit(
            client, teacher, room.course_id, question["id"], status="approved"
        )
        assert response.status_code == 200, response.text
    return room, topic, made


def generation_logs(db, course_id: str) -> list[InteractionLog]:
    return list(
        db.scalars(
            select(InteractionLog).where(
                InteractionLog.course_id == course_id,
                InteractionLog.kind == "quiz_generation",
            )
        )
    )


def test_drafts_are_grounded_pending_and_logged(
    client, db, llm, teacher, student
) -> None:
    room, topic, made = generated(client, llm, teacher, student)

    assert len(made) == 3
    first = made[0]
    assert first["status"] == "pending"
    assert first["origin"] == "ai"
    assert first["topic_id"] == topic["id"]
    assert first["topic_name"] == "Paréntesis"
    assert first["statement"] == "¿Cuánto vale 2(x - 3) sin paréntesis?"
    assert sorted(first["options"]) == ["2x + 6", "2x - 3", "2x - 6", "x - 6"]
    # The right answer is moved to a different position in each draft.
    assert [q["options"][q["correct_option"]] for q in made] == ["2x - 6"] * 3
    assert [q["correct_option"] for q in made] == [0, 1, 2]
    assert "F1" not in first["explanation"]
    assert [q["difficulty"] for q in made] == [1, 2, 3]
    assert [c["location_label"] for c in first["citations"]] == [f"§ {SECTION}"]
    assert (first["answered_count"], first["correct_rate"]) == (0, None)

    # Only the topic's material, no personal data.
    system, messages = llm.chat_calls[-1]
    content = messages[-1]["content"]
    assert "Quitar paréntesis" in content and "Transponer términos" not in content
    assert student.display_name not in content + system
    assert teacher.display_name not in content + system

    [log] = generation_logs(db, room.course_id)
    assert (log.outcome, log.model, log.student_ref) == ("answer", "fake-model", None)
    assert log.input_tokens > 0
    allowance = client.get("/v1/student/allowance", headers=student.headers).json()
    assert allowance["used"] == 0


def test_count_defaults_to_five_and_is_bounded(client, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    topic = topic_with_material(client, teacher, room.course_id, room.document["id"])
    llm.reply = {"questions": [draft(f"Pregunta {i}") for i in range(8)]}

    default = generate(client, teacher, room.course_id, topic["id"], count=None)
    too_many = generate(client, teacher, room.course_id, topic["id"], count=11)
    none = generate(client, teacher, room.course_id, topic["id"], count=0)

    assert len(default.json()["questions"]) == 5
    assert "5" in llm.chat_calls[0][1][-1]["content"]
    assert too_many.status_code == none.status_code == 422


def test_unusable_drafts_are_dropped(client, llm, teacher, student) -> None:
    bad_options = draft("Opciones repetidas") | {"options": ["a", "a", "b", "c"]}
    three_options = draft("Tres opciones") | {"options": ["a", "b", "c"]}
    replies = {
        "questions": [
            draft("Buena"),
            bad_options,
            three_options,
            draft("Sin correcta", correct="E"),
            draft("Cita inventada", cited=["F9"]),
            draft(" "),
            "no es un objeto",
        ]
    }

    _, _, made = generated(client, llm, teacher, student, replies)

    assert [q["statement"] for q in made] == ["Buena"]


def test_a_reply_with_nothing_usable_is_no_source(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    topic = topic_with_material(client, teacher, room.course_id, room.document["id"])
    llm.reply = {"questions": [draft("Cita inventada", cited=["F7"])]}

    response = generate(client, teacher, room.course_id, topic["id"])

    assert response.status_code == 201
    assert response.json() == {"kind": "no_source", "questions": []}


def test_a_topic_without_material_does_not_call_the_model(
    client, db, llm, teacher
) -> None:
    course = create_course(client, teacher)
    topic = create_topic(client, teacher, course["id"], "Paréntesis").json()

    response = generate(client, teacher, course["id"], topic["id"])

    assert response.json() == {"kind": "no_source", "questions": []}
    assert llm.chat_calls == []
    [log] = generation_logs(db, course["id"])
    assert log.outcome == "no_source"


def test_a_topic_without_assignments_uses_similar_material(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    topic = create_topic(
        client, teacher, room.course_id, "Quitar paréntesis multiplicando"
    ).json()
    llm.reply = DRAFTS

    response = generate(client, teacher, room.course_id, topic["id"])

    assert response.json()["kind"] == "answer"
    assert "Quitar paréntesis" in llm.chat_calls[-1][1][-1]["content"]


def test_provider_failure_stores_nothing(client, db, llm, teacher, student) -> None:
    room = classroom(client, teacher, student)
    topic = topic_with_material(client, teacher, room.course_id, room.document["id"])
    llm.fail_chat = True

    response = generate(client, teacher, room.course_id, topic["id"])

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "tutor_unavailable"
    listed = client.get(questions_path(room.course_id), headers=teacher.headers)
    assert listed.json()["total"] == 0
    [log] = generation_logs(db, room.course_id)
    assert (log.outcome, log.error_code) == ("error", "tutor_unavailable")


def test_repeated_statements_are_not_stored_twice(
    client, llm, teacher, student
) -> None:
    room, topic, _ = generated(client, llm, teacher, student)

    again = generate(client, teacher, room.course_id, topic["id"]).json()

    assert again == {"kind": "no_source", "questions": []}


def test_list_filters_and_counts(client, llm, teacher, student) -> None:
    room, topic, made = generated(client, llm, teacher, student)
    edit(client, teacher, room.course_id, made[0]["id"], status="approved")
    edit(client, teacher, room.course_id, made[1]["id"], status="rejected")

    everything = client.get(questions_path(room.course_id), headers=teacher.headers)
    pending = client.get(
        f"{questions_path(room.course_id)}?status=pending&topic_id={topic['id']}",
        headers=teacher.headers,
    )

    assert everything.json()["total"] == 3
    assert everything.json()["counts"] == {"pending": 1, "approved": 1, "rejected": 1}
    assert [q["id"] for q in pending.json()["items"]] == [made[2]["id"]]
    assert pending.json()["counts"] == {"pending": 1, "approved": 1, "rejected": 1}


def test_edit_and_approve_in_one_request(client, llm, teacher, student) -> None:
    room, _, made = generated(client, llm, teacher, student)

    response = edit(
        client,
        teacher,
        room.course_id,
        made[0]["id"],
        statement="¿Qué queda al quitar el paréntesis en 2(x - 3)?",
        options=["2x - 6", "2x - 3", "2x + 6", "x - 6"],
        correct_option=0,
        explanation="El 2 multiplica a x y a -3.",
        difficulty=2,
        status="approved",
    )

    assert response.status_code == 200, response.text
    question = response.json()
    assert question["status"] == "approved"
    assert question["origin"] == "edited"
    assert question["correct_option"] == 0
    assert question["difficulty"] == 2
    assert question["reviewed_at"] is not None


def test_approving_without_edits_keeps_the_ai_origin(
    client, llm, teacher, student
) -> None:
    room, _, made = generated(client, llm, teacher, student)

    question = edit(client, teacher, room.course_id, made[0]["id"], status="approved")

    assert question.json()["origin"] == "ai"


def test_invalid_edits_are_rejected(client, llm, teacher, student) -> None:
    room, _, made = generated(client, llm, teacher, student)
    question_id = made[0]["id"]

    for changes in (
        {"options": ["a", "b", "c"]},
        {"options": ["a", "b", "b", "c"]},
        {"options": ["a", "b", "c", " "]},
        {"correct_option": 4},
        {"difficulty": 0},
        {"difficulty": 4},
        {"statement": ""},
        {"status": "archived"},
    ):
        response = edit(client, teacher, room.course_id, question_id, **changes)
        assert response.status_code == 422, changes


def test_other_teachers_get_404(client, llm, teacher, other_teacher, student) -> None:
    room, topic, made = generated(client, llm, teacher, student)

    responses = [
        generate(client, other_teacher, room.course_id, topic["id"]),
        client.get(questions_path(room.course_id), headers=other_teacher.headers),
        edit(client, other_teacher, room.course_id, made[0]["id"], status="approved"),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404]


def test_students_cannot_use_teacher_routes(client, llm, teacher, student) -> None:
    room, _, _ = generated(client, llm, teacher, student)

    response = client.get(questions_path(room.course_id), headers=student.headers)

    assert response.status_code == 403
