import json
from collections.abc import AsyncGenerator

import asyncio

from app.ai.memory.long_term import add_conversation_turn, load_long_term
from app.ai.memory.short_term import append_turn, load_short_term, maybe_summarize
from app.ai.memory.schemas import MemoryContext
from app.ai.retrievers.hybrid_retriever import hybrid_retrieve
from app.infra.db import AsyncSessionLocal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag_graph import SYSTEM_PROMPT
from app.core.settings import settings
from app.models.chat import QAMessage, QASession
from app.schemas.chat import Citation

async def build_memory_context(
    user_id: int,
    session_id: int,
    question: str,
) -> MemoryContext:
    """合并 Redis 短期 + Mem0 长期"""
    short = await load_short_term(session_id)
    long = await load_long_term(user_id, session_id, question)
    return MemoryContext(
        session_summary=short.session_summary,
        recent_turns=short.recent_turns,
        user_memories=long.user_memories,
        session_memories=long.session_memories,
    )

async def _after_message_persisted(
    *,
    user_id: int,
    session_id: int,
    question: str,
    answer: str,
) -> None:
    """PG 落库后：更新 Redis + 异步 Mem0"""
    await append_turn(session_id, "user", question)
    await append_turn(session_id, "assistant", answer)
    await maybe_summarize(session_id)
    asyncio.create_task(
        add_conversation_turn(user_id, session_id, question, answer)
    )

def chunks_to_citations(chunks: list[dict]) -> list[Citation]:
    citations = []
    for c in chunks:
        snippet = c["content"][:200]
        citations.append(
            Citation(
                document_id=c["document_id"],
                chunk_id=c["chunk_id"],
                title=c["title"],
                snippet=snippet,
                score=c.get("score"),
            )
        )
    return citations


async def create_session(db: AsyncSession, user_id: int, title: str) -> QASession:
    session = QASession(user_id=user_id, title=title)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_user_session(db: AsyncSession, session_id: int, user_id: int) -> QASession | None:
    result = await db.execute(select(QASession).where(QASession.id == session_id, QASession.user_id == user_id))
    return result.scalar_one_or_none()


async def save_message(
    db: AsyncSession,
    session_id: int,
    role: str,
    content: str,
    citations: list[Citation] | None = None,
) -> QAMessage:
    msg = QAMessage(
        session_id=session_id,
        role=role,
        content=content,
        citations=[c.model_dump() for c in citations] if citations else None,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def ask_in_session(
    db: AsyncSession,
    session: QASession,
    question: str,
    owner_ids: list[int] | None,
    memory: MemoryContext | None = None,
) -> tuple[QAMessage, QAMessage, list[Citation]]:
    from app.ai.rag_graph import run_rag

    user_msg = await save_message(db, session.id, "user", question)

    # 首条消息时，用问题作为会话标题
    if session.title == "新对话":
        session.title = question[:50]
    
    # 1. 读记忆（注意：不含本轮 user 消息，避免重复）
    memory = await build_memory_context(session.user_id, session.id, question)

    answer, chunks = await run_rag(question, owner_ids, memory=memory)
    citations = chunks_to_citations(chunks)
    assistant_msg = await save_message(db, session.id, "assistant", answer, citations)

       # 3. 更新 Redis / Mem0
    await _after_message_persisted(
        user_id=session.user_id,
        session_id=session.id,
        question=question,
        answer=answer,
    )

    return user_msg, assistant_msg, citations

async def stream_answer(question: str,
    owner_ids: list[int] | None,
    *,
    user_id: int,
    session_id: int,
    memory: MemoryContext | None = None,
) -> AsyncGenerator[str, None]:
    from app.ai.memory.prompt import SYSTEM_PROMPT, build_user_prompt

    memory = memory or await build_memory_context(user_id, session_id, question)

    """SSE 流式输出：先检索，再流式生成"""
    async with AsyncSessionLocal() as db:
        hits = await hybrid_retrieve(db, question, owner_ids, settings.rag_top_k)
    chunks = [h.to_dict() for h in hits]

    if not chunks and not memory.has_content():
        yield json.dumps({"type": "token", "content": "未找到相关文档，请先上传资料后再提问。"})
        yield json.dumps({"type": "done", "citations": []})
        return

    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] 文档《{c['title']}》\n{c['content']}")
    context = "\n\n".join(parts)
    citations = [c.model_dump() for c in chunks_to_citations(chunks)]
    user_prompt = build_user_prompt(question=question, rag_context=context, memory=memory)

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
        streaming=True,
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    full: list[str] = []
    async for chunk in llm.astream(messages):
        if chunk.content:
            full.append(chunk.content)
            yield json.dumps({"type": "token", "content": chunk.content})

    yield json.dumps({"type": "done", "citations": citations})