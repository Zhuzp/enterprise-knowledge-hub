"""analyze 节点：LLM 路由解析与降级"""

import json

import pytest

from app.ai.agents.analyze import analyze_question
from app.ai.agents.schemas import Complexity, Intent, RoutePath
from app.ai.memory.schemas import ChatTurn, MemoryContext


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    async def ainvoke(self, _messages):
        class Resp:
            pass

        r = Resp()
        r.content = self._content
        return r


@pytest.mark.asyncio
async def test_analyze_chitchat_routes_direct(monkeypatch):
    payload = json.dumps(
        {
            "intent": "chitchat",
            "complexity": "simple",
            "needs_hybrid": False,
            "needs_graph": False,
            "needs_rewrite": False,
            "reasoning": "寒暄",
        }
    )
    monkeypatch.setattr("app.ai.agents.analyze._get_llm", lambda: _FakeLLM(payload))

    decision = await analyze_question("你好")
    assert decision.intent == Intent.CHITCHAT
    assert decision.path == RoutePath.DIRECT
    assert decision.needs_hybrid is False


@pytest.mark.asyncio
async def test_analyze_multi_hop_routes_full(monkeypatch):
    payload = json.dumps(
        {
            "intent": "multi_hop",
            "complexity": "complex",
            "needs_hybrid": True,
            "needs_graph": True,
            "needs_rewrite": True,
            "reasoning": "跨实体多跳",
        }
    )
    monkeypatch.setattr("app.ai.agents.analyze._get_llm", lambda: _FakeLLM(payload))

    decision = await analyze_question("张三的上级部门负责哪些制度？")
    assert decision.path == RoutePath.FULL
    assert decision.needs_graph is True
    assert decision.needs_rewrite is True


@pytest.mark.asyncio
async def test_analyze_invalid_json_fallback_hybrid(monkeypatch):
    monkeypatch.setattr("app.ai.agents.analyze._get_llm", lambda: _FakeLLM("not json"))

    decision = await analyze_question("报销上限")
    assert decision.path == RoutePath.HYBRID
    assert decision.intent == Intent.FACT_LOOKUP
    assert "降级" in decision.reasoning


@pytest.mark.asyncio
async def test_analyze_invalid_enum_fallback_hybrid(monkeypatch):
    payload = json.dumps(
        {
            "intent": "unknown_intent",
            "complexity": "simple",
            "needs_hybrid": True,
        }
    )
    monkeypatch.setattr("app.ai.agents.analyze._get_llm", lambda: _FakeLLM(payload))

    decision = await analyze_question("测试")
    assert decision.path == RoutePath.HYBRID
    assert "枚举" in decision.reasoning


@pytest.mark.asyncio
async def test_analyze_includes_memory_hint(monkeypatch):
    captured: list = []

    class _CapturingLLM:
        async def ainvoke(self, messages):
            captured.extend(messages)
            return await _FakeLLM(
                json.dumps(
                    {
                        "intent": "fact_lookup",
                        "complexity": "simple",
                        "needs_hybrid": True,
                        "needs_graph": False,
                        "needs_rewrite": True,
                        "reasoning": "指代",
                    }
                )
            ).ainvoke(messages)

    monkeypatch.setattr("app.ai.agents.analyze._get_llm", _CapturingLLM)

    memory = MemoryContext(
        session_summary="刚讨论报销流程",
        recent_turns=[ChatTurn(role="user", content="第二步是什么")],
    )
    decision = await analyze_question("它需要什么材料？", memory=memory)

    user_msg = captured[1].content
    assert "刚讨论报销流程" in user_msg
    assert decision.needs_rewrite is True
    assert decision.complexity == Complexity.SIMPLE
