"""US4 — daily message allowance shared across courses (FR-060, FR-061, SC-007)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.services import allowance
from tests.api.helpers import COVERED_QUESTION, ask, classroom, open_conversation
from tests.fakes import insert_auth_user


def test_allowance_reports_limit_and_reset(client, student) -> None:
    body = client.get("/v1/student/allowance", headers=student.headers).json()

    assert body["limit"] == 5
    assert body["used"] == 0
    assert body["remaining"] == 5
    resets_at = datetime.fromisoformat(body["resets_at"])
    assert resets_at.tzinfo is not None
    assert (resets_at.hour, resets_at.minute) == (0, 0)


def test_limit_reached_blocks_before_calling_the_model(
    client, teacher, student, llm
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    for _ in range(5):
        response = ask(
            client, student, room.course_id, conversation["id"], COVERED_QUESTION
        )
        assert response.status_code == 201
    assert response.json()["allowance"]["remaining"] == 0
    calls_before = len(llm.chat_calls)

    blocked = ask(client, student, room.course_id, conversation["id"], "Otra")

    assert blocked.status_code == 429
    error = blocked.json()["error"]
    assert error["code"] == "daily_limit_reached"
    assert "resets_at" in error["details"]
    assert len(llm.chat_calls) == calls_before


def test_allowance_is_shared_across_courses(client, teacher, student) -> None:
    first = classroom(client, teacher, student)
    second = classroom(client, teacher, student)
    for room in (first, second):
        conversation = open_conversation(client, student, room.course_id)
        ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)

    body = client.get("/v1/student/allowance", headers=student.headers).json()
    assert body["used"] == 2


def test_concurrent_reservations_never_exceed_the_limit(engine) -> None:
    settings = get_settings()
    factory = sessionmaker(bind=engine)
    with factory() as session:
        student_id = insert_auth_user(session, None, "Concurrencia")
        session.commit()

    def reserve(_: int) -> bool:
        with factory() as session:
            reserved = allowance.reserve(session, settings, student_id)
            session.commit()
            return reserved is not None

    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(reserve, range(10)))
        assert sum(results) == settings.daily_message_limit == 5
    finally:
        with factory() as session:
            session.execute(
                text("delete from auth.users where id = :id"), {"id": student_id}
            )
            session.commit()
