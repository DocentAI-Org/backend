"""Each call names its task, so it reaches the provider and model for it (spec 014)."""

from tests.api.helpers import COVERED_QUESTION, ask, classroom, open_conversation
from tests.api.test_us7_exercises import MISTAKE, submit


def test_the_tutor_and_the_feedback_ask_for_their_task(
    client, llm, teacher, student
) -> None:
    room = classroom(client, teacher, student)
    conversation = open_conversation(client, student, room.course_id)
    ask(client, student, room.course_id, conversation["id"], COVERED_QUESTION)
    llm.reply = MISTAKE
    submit(client, student, room.course_id)

    assert llm.tasks == ["tutor", "feedback"]
