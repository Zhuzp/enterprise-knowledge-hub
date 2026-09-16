"""Langfuse 接入：开关 + CallbackHandler + chat 级 trace 上下文。"""

from __future__ import annotations

import logging
import random
from contextlib import contextmanager
from typing import Any, Generator

from app.core.settings import settings

logger = logging.getLogger(__name__)


def is_langfuse_enabled() -> bool:
    if not settings.langfuse_enabled:
        return False
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return False
    if settings.langfuse_sample_rate < 1.0 and random.random() > settings.langfuse_sample_rate:
        return False
    return True


def get_langchain_handler():
    """每次请求新建 Handler（官方推荐），未启用返回 None。"""
    if not is_langfuse_enabled():
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        logger.exception("Langfuse CallbackHandler 初始化失败")
        return None


def flush_langfuse() -> None:
    if not settings.langfuse_enabled:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        logger.warning("Langfuse flush 失败", exc_info=True)


@contextmanager
def trace_chat(
    *,
    name: str,
    user_id: int,
    session_id: int,
    question: str,
    stream: bool,
    tags: list[str] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    包住一次问答。yield 的 ctx 里有：
      - handler: CallbackHandler | None
      - config: 可直接传给 LangGraph / LLM 的 RunnableConfig 片段
      - update(output=..., metadata=...): 结束时补 citations / route
    """
    empty: dict[str, Any] = {
        "handler": None,
        "config": {},
        "update": lambda **kwargs: None,
    }

    if not is_langfuse_enabled():
        yield empty
        return

    try:
        from langfuse import get_client, propagate_attributes

        langfuse = get_client()
        handler = get_langchain_handler()
    except Exception:
        logger.exception("Langfuse setup 失败，降级为无观测执行")
        yield empty
        return

    tag_list = list(tags or [])
    tag_list.append("stream" if stream else "non_stream")

    cfg: dict[str, Any] = {
        "metadata": {
            "langfuse_user_id": str(user_id),
            "langfuse_session_id": str(session_id),
            "langfuse_tags": tag_list,
        }
    }
    if handler is not None:
        cfg["callbacks"] = [handler]

    yielded = False
    try:
        with langfuse.start_as_current_observation(as_type="span", name=name) as root:
            root.update(
                input={"question": question[:2000]},
                metadata={"stream": stream},
            )

            def _update(**kwargs: Any) -> None:
                try:
                    root.update(**kwargs)
                except Exception:
                    logger.debug("langfuse root.update failed", exc_info=True)

            with propagate_attributes(
                user_id=str(user_id),
                session_id=str(session_id),
                tags=tag_list,
                metadata={
                    "app": "enterprise-knowledge-hub",
                    "stream": stream,
                },
            ):
                yielded = True
                yield {
                    "handler": handler,
                    "config": cfg,
                    "update": _update,
                }

            if handler is not None and getattr(handler, "last_trace_id", None):
                logger.info(
                    "langfuse trace_id=%s session_id=%s",
                    handler.last_trace_id,
                    session_id,
                )
    except Exception:
        if not yielded:
            logger.exception("Langfuse 建 trace 失败，降级为无观测执行")
            yield empty
            return
        raise
