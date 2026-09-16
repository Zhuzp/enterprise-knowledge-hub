import json
import logging
from collections.abc import AsyncGenerator

import asyncio

logger = logging.getLogger(__name__)

_STREAM_ERROR_MSG = "抱歉，处理问题时出错了，请稍后重试。"

from app.ai.memory.long_term import add_conversation_turn, load_long_term
from app.ai.memory.short_term import append_turn, load_short_term_with_pg_fallback, maybe_summarize
from app.ai.memory.schemas import MemoryContext
from app.ai.memory.prompt import SYSTEM_PROMPT, build_user_prompt

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.chat import QAMessage, QASession
from app.schemas.chat import Citation

async def build_memory_context(
    user_id: int,
    session_id: int,
    question: str,
) -> MemoryContext:
    """合并 Redis 短期（PG 回填兜底）+ Mem0 长期"""
    short = await load_short_term_with_pg_fallback(session_id)
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
) -> tuple[QAMessage, QAMessage, list[Citation]]:
    from app.ai.agents.agentic_rag_graph import run_agentic_rag
    from app.observability import trace_chat

    user_msg = await save_message(db, session.id, "user", question)

    if session.title == "新对话":
        session.title = question[:50]

    memory = await build_memory_context(session.user_id, session.id, question)

    with trace_chat(
        name="chat.ask",
        user_id=session.user_id,
        session_id=session.id,
        question=question,
        stream=False,
        tags=["rag", "agentic"],
    ) as obs:
        answer, chunks, route_meta = await run_agentic_rag(
            question,
            owner_ids,
            memory=memory,
            config=obs["config"],
        )
        citations = chunks_to_citations(chunks)
        obs["update"](
            output={
                "answer": answer[:4000],
                "citation_chunk_ids": [c.chunk_id for c in citations],
            },
            metadata={
                "route": route_meta.get("route"),
                "chunk_count": len(chunks),
                "has_graph_reasoning": bool(route_meta.get("graph_reasoning")),
            },
        )

    assistant_msg = await save_message(db, session.id, "assistant", answer, citations)

    await _after_message_persisted(
        user_id=session.user_id,
        session_id=session.id,
        question=question,
        answer=answer,
    )

    return user_msg, assistant_msg, citations


async def stream_answer(
    question: str,
    owner_ids: list[int] | None,
    *,
    user_id: int,
    session_id: int,
    memory: MemoryContext | None = None,
) -> AsyncGenerator[str, None]:
    """SSE 流式输出：Agentic 检索 + 流式生成"""
    from app.ai.agents.agentic_rag_graph import run_agentic_retrieve
    from app.ai.agents.schemas import RoutePath
    from app.observability import trace_chat

    memory = memory or await build_memory_context(user_id, session_id, question)

    with trace_chat(
        name="chat.ask.stream",
        user_id=user_id,
        session_id=session_id,
        question=question,
        stream=True,
        tags=["rag", "agentic"],
    ) as obs:
        lf_config = obs["config"]

        try:
            context, chunks, meta, decision = await run_agentic_retrieve(
                question,
                owner_ids,
                memory=memory,
                config=lf_config,
            )
        except Exception:
            logger.exception("agentic retrieve failed session_id=%s", session_id)
            obs["update"](level="ERROR", status_message="retrieve_failed")
            yield json.dumps({"type": "token", "content": _STREAM_ERROR_MSG})
            yield json.dumps({"type": "done", "citations": []})
            return

        if decision.path == RoutePath.DIRECT:
            if not memory.has_content():
                msg = "你好！我是企业知识库助手，请上传资料或直接提问业务问题。"
                obs["update"](output={"answer": msg}, metadata={"route": decision.model_dump()})
                yield json.dumps({"type": "token", "content": msg})
                yield json.dumps({"type": "done", "citations": []})
                return
            context = ""

        if not context and not memory.has_content():
            msg = "未找到相关文档，请先上传资料后再提问。"
            obs["update"](output={"answer": msg}, metadata={"route": decision.model_dump()})
            yield json.dumps({"type": "token", "content": msg})
            yield json.dumps({"type": "done", "citations": []})
            return

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

        answer_parts: list[str] = []
        try:
            async for chunk in llm.astream(messages, config=lf_config):
                if chunk.content:
                    answer_parts.append(chunk.content)
                    yield json.dumps({"type": "token", "content": chunk.content})
        except Exception:
            logger.exception("llm stream failed session_id=%s", session_id)
            obs["update"](level="ERROR", status_message="llm_stream_failed")
            yield json.dumps({"type": "token", "content": _STREAM_ERROR_MSG})
            yield json.dumps({"type": "done", "citations": citations})
            return

        obs["update"](
            output={
                "answer": "".join(answer_parts)[:4000],
                "citation_chunk_ids": [c["chunk_id"] for c in citations],
            },
            metadata={
                "route": meta.get("route"),
                "chunk_count": len(chunks),
                "has_graph_reasoning": bool(meta.get("graph_reasoning")),
            },
        )

        yield json.dumps({"type": "done", "citations": citations})
