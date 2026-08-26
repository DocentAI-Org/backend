from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    student_id: str | None = None
    course_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    detected_skills: list[str] = []


@router.post("", response_model=ChatResponse)
def create_chat_response(payload: ChatRequest) -> ChatResponse:
    return ChatResponse(
        answer=(
            "Base endpoint ready. The next step is to connect curriculum "
            "retrieval, OpenAI, and student progress tracking."
        ),
        sources=[],
        detected_skills=[]
    )
