import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.ai.memory.schemas import ChatTurn, MemoryContext
from app.core.settings import settings
from app.infra.redis_client import get_redis

logger = logging.getLogger(__name__)

WINDOW_KEY = "chat:st:{session_id}:window"
SUMMARY_KEY = "chat:st:{session_id}:summary"

SUMMARY_PROMPT = """请将以下对话历史压缩成一段简洁中文摘要，保留关键事实、结论和用户偏好。
不要逐句复述，控制在 200 字以内。

已有摘要（如有）：
{existing_summary}

待合并的新对话：
{new_dialogue}
"""


def _window_key(session_id: int) -> str:
    return WINDOW_KEY.format(session_id=session_id)


def _summary_key(session_id: int) -> str:
    return SUMMARY_KEY.format(session_id=session_id)


async def load_short_term(session_id: int) -> MemoryContext:
    """读 Redis：摘要 + 滑动窗口"""
    redis = get_redis()
    raw_window = await redis.lrange(_window_key(session_id), 0, -1)
    summary = await redis.get(_summary_key(session_id)) or ""

    turns = [ChatTurn(**json.loads(item)) for item in raw_window]
    return MemoryContext(session_summary=summary, recent_turns=turns)


async def append_turn(session_id: int, role: str, content: str) -> None:
    """追加一条消息到窗口"""
    redis = get_redis()
    key = _window_key(session_id)
    item = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    await redis.rpush(key, item)
    # 只保留最近 N*2 条（N 轮 = user+assistant）
    max_len = settings.memory_window_size * 2
    await redis.ltrim(key, -max_len, -1)
    await redis.expire(key, settings.memory_session_ttl_seconds)
    await redis.expire(_summary_key(session_id), settings.memory_session_ttl_seconds)


async def maybe_summarize(session_id: int) -> None:
    """窗口过长时，把老消息合并进 summary"""
    redis = get_redis()
    key = _window_key(session_id)
    length = await redis.llen(key)
    if length <= settings.memory_summary_trigger:
        return

    # 取出最老的一半，做摘要后删掉
    trim_count = length // 2
    old_items = await redis.lrange(key, 0, trim_count - 1)
    if not old_items:
        return

    old_turns = [ChatTurn(**json.loads(x)) for x in old_items]
    dialogue = "\n".join(f"{t.role}: {t.content}" for t in old_turns)
    existing = await redis.get(_summary_key(session_id)) or ""

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )
    try:
        resp = await llm.ainvoke([
            SystemMessage(content="你是对话摘要助手。"),
            HumanMessage(content=SUMMARY_PROMPT.format(
                existing_summary=existing or "（无）",
                new_dialogue=dialogue,
            )),
        ])
        new_summary = (resp.content or "").strip()
        if new_summary:
            await redis.set(_summary_key(session_id), new_summary)
            await redis.expire(_summary_key(session_id), settings.memory_session_ttl_seconds)
        # 从 window 左侧删掉已摘要的部分
        for _ in range(trim_count):
            await redis.lpop(key)
    except Exception:
        logger.exception("会话摘要失败 session_id=%s", session_id)


async def fetch_recent_turns_from_pg(session_id: int) -> list[ChatTurn]:
    """从 qa_messages 取最近 N 轮对话（不含本轮尚未落库的消息）"""
    from sqlalchemy import select

    from app.infra.db import AsyncSessionLocal
    from app.models.chat import QAMessage

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(QAMessage)
            .where(QAMessage.session_id == session_id)
            .order_by(QAMessage.created_at.asc())
        )
        messages = result.scalars().all()

    max_len = settings.memory_window_size * 2
    recent = messages[-max_len:]
    return [ChatTurn(role=m.role, content=m.content) for m in recent]


async def restore_redis_window(session_id: int, turns: list[ChatTurn]) -> None:
    """PG 回填后写回 Redis，避免下次再查库"""
    if not turns:
        return
    redis = get_redis()
    key = _window_key(session_id)
    await redis.delete(key)
    for turn in turns:
        item = json.dumps({"role": turn.role, "content": turn.content}, ensure_ascii=False)
        await redis.rpush(key, item)
    await redis.expire(key, settings.memory_session_ttl_seconds)
    if await redis.get(_summary_key(session_id)):
        await redis.expire(_summary_key(session_id), settings.memory_session_ttl_seconds)


async def load_short_term_with_pg_fallback(session_id: int) -> MemoryContext:
    """读 Redis；window 为空时从 PG 回填 recent_turns 并预热 Redis"""
    ctx = await load_short_term(session_id)
    if ctx.recent_turns:
        return ctx

    turns = await fetch_recent_turns_from_pg(session_id)
    if not turns:
        return ctx

    logger.info("Redis window 为空，PG 回填 session_id=%s turns=%d", session_id, len(turns))
    ctx.recent_turns = turns
    await restore_redis_window(session_id, turns)
    return ctx