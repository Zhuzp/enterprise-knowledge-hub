"""记忆上下文与 prompt 拼装"""

from app.ai.memory.prompt import SYSTEM_PROMPT, build_user_prompt
from app.ai.memory.schemas import ChatTurn, MemoryContext


def test_memory_context_has_content():
    empty = MemoryContext()
    assert not empty.has_content()

    filled = MemoryContext(
        session_summary="用户在问报销",
        recent_turns=[ChatTurn(role="user", content="你好")],
    )
    assert filled.has_content()


def test_build_user_prompt_orders_sections():
    memory = MemoryContext(
        user_memories=["偏好简洁回答"],
        session_summary="讨论过差旅报销",
        recent_turns=[ChatTurn(role="user", content="上限多少")],
    )
    prompt = build_user_prompt(
        question="那住宿呢？",
        rag_context="[1] 差旅标准：住宿 500/晚",
        memory=memory,
    )
    assert prompt.index("【用户长期记忆】") < prompt.index("【对话摘要】")
    assert prompt.index("【对话摘要】") < prompt.index("【最近对话】")
    assert prompt.index("【参考资料】") < prompt.index("【当前问题】")
    assert "那住宿呢？" in prompt
    assert SYSTEM_PROMPT  # 常量可被 generate 节点引用
