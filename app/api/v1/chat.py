import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.settings import settings
from app.infra.db import get_db
from app.models.chat import QAMessage, QASession
from app.models.user import User
from app.schemas.chat import (
    ChatAnswerResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    Citation,
)
from app.services.chat_service import ask_in_session, build_memory_context, create_session, get_user_session, save_message, stream_answer
from app.services.permission_service import get_accessible_owner_ids

router = APIRouter()


def _llm_configured() -> bool:
    return bool(settings.openai_api_key and settings.openai_api_key.strip())


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_session(db, current_user.id, data.title)


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QASession).where(QASession.user_id == current_user.id).order_by(QASession.created_at.desc())
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def list_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_user_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(QAMessage).where(QAMessage.session_id == session_id).order_by(QAMessage.created_at.asc())
    )
    return result.scalars().all()


@router.post("/sessions/{session_id}/messages", response_model=ChatAnswerResponse)
async def send_message(
    session_id: int,
    data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在 .env 设置 OPENAI_API_KEY",
        )

    session = await get_user_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    owner_ids = await get_accessible_owner_ids(db, current_user)

    user_msg, assistant_msg, citations = await ask_in_session(db, session, data.question, owner_ids)

    return ChatAnswerResponse(
        answer=assistant_msg.content,
        citations=citations,
        user_message=ChatMessageResponse.model_validate(user_msg),
        assistant_message=ChatMessageResponse.model_validate(assistant_msg),
    )


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(
    session_id: int,
    data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _llm_configured():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")

    session = await get_user_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    owner_ids = await get_accessible_owner_ids(db, current_user)

    await save_message(db, session.id, "user", data.question)
    if session.title == "新对话":
        session.title = data.question[:50]
    await db.flush()

    memory = await build_memory_context(current_user.id, session.id, data.question)

    async def event_generator():
        full_answer: list[str] = []
        citations_data: list[dict] = []

        async for line in stream_answer(
            data.question, 
            owner_ids,
            user_id=current_user.id,
            session_id=session.id,
            memory=memory,
        ):
            payload = json.loads(line)
            if payload["type"] == "token":
                full_answer.append(payload["content"])
            if payload["type"] == "done":
                citations_data = payload.get("citations", [])
            yield f"data: {line}\n\n"

        answer_text = "".join(full_answer)
        citations = [Citation(**c) for c in citations_data]
        await save_message(db, session.id, "assistant", answer_text, citations)

        from app.services.chat_service import _after_message_persisted
        await _after_message_persisted(
            user_id=current_user.id,
            session_id=session.id,
            question=data.question,
            answer=answer_text,
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")
