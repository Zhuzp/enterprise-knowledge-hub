from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    document_id: int
    chunk_id: int
    title: str
    snippet: str
    score: float | None = None


class ChatSessionCreate(BaseModel):
    title: str = Field(default="新对话", max_length=200)


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    created_at: datetime


class ChatMessageCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    stream: bool = False


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    citations: list[Citation] | None = None
    created_at: datetime


class ChatAnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
