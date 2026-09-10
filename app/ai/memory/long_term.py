import asyncio
import logging
from typing import Any

from app.ai.memory.schemas import MemoryContext
from app.core.settings import settings

logger = logging.getLogger(__name__)

_memory = None


def _build_mem0_config() -> dict[str, Any]:
    """Mem0 OSS：LLM 抽记忆 + Embedder 向量化 + pgvector 存储"""
    llm_model = settings.mem0_llm_model or settings.openai_model
    embed_model = settings.mem0_embedding_model or settings.embedding_model

    return {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "connection_string": settings.pg_connection_string,
                "collection_name": settings.mem0_collection_name,
                "embedding_model_dims": settings.embedding_dims,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": embed_model,
                "api_key": settings.openai_api_key,
                "openai_base_url": settings.openai_base_url,
                "embedding_dims": settings.embedding_dims,
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": llm_model,
                "api_key": settings.openai_api_key,
                "openai_base_url": settings.openai_base_url,
                "temperature": 0,
            },
        },
    }


def _get_mem0():
    global _memory
    if not settings.mem0_enabled:
        return None
    if not settings.openai_api_key:
        logger.warning("mem0_enabled=true 但未配置 openai_api_key，Mem0 未初始化")
        return None
    if _memory is None:
        from mem0 import Memory

        _memory = Memory.from_config(_build_mem0_config())
        logger.info(
            "Mem0 已初始化 collection=%s dims=%s",
            settings.mem0_collection_name,
            settings.embedding_dims,
        )
    return _memory


async def load_long_term(
    user_id: int,
    session_id: int,
    question: str,
) -> MemoryContext:
    """检索用户级 + 会话级记忆"""
    mem = _get_mem0()
    ctx = MemoryContext()
    if mem is None:
        return ctx

    uid = str(user_id)
    sid = str(session_id)

    def _search():
        user_hits = mem.search(question, user_id=uid, limit=settings.mem0_top_k_user)
        session_hits = mem.search(question, user_id=uid, run_id=sid, limit=settings.mem0_top_k_session)
        return user_hits, session_hits

    try:
        user_hits, session_hits = await asyncio.to_thread(_search)
        ctx.user_memories = _extract_texts(user_hits)
        ctx.session_memories = _extract_texts(session_hits)
    except Exception:
        logger.exception("Mem0 search 失败 user=%s session=%s", user_id, session_id)
    return ctx


async def add_conversation_turn(
    user_id: int,
    session_id: int,
    user_content: str,
    assistant_content: str,
) -> None:
    """异步写入 Mem0（在 chat_service 里 create_task 调用）"""
    mem = _get_mem0()
    if mem is None:
        return

    uid = str(user_id)
    sid = str(session_id)
    messages = [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content},
    ]

    def _add():
        mem.add(messages, user_id=uid, metadata={"scope": "user"})
        mem.add(messages, user_id=uid, run_id=sid, metadata={"scope": "session"})

    try:
        await asyncio.to_thread(_add)
    except Exception:
        logger.exception("Mem0 add 失败 user=%s session=%s", user_id, session_id)


def _extract_texts(hits: Any) -> list[str]:
    """兼容 mem0 不同版本返回格式"""
    if not hits:
        return []
    if isinstance(hits, dict):
        hits = hits.get("results") or hits.get("memories") or []
    texts: list[str] = []
    for item in hits:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            texts.append(item.get("memory") or item.get("text") or "")
    return [t for t in texts if t.strip()]
