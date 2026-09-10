"""意图识别 + 复杂度判别"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.ai.agents.schemas import (
    Complexity,
    Intent,
    RouteDecision,
    RoutePath,
)
from app.ai.memory.schemas import MemoryContext
from app.core.settings import settings

ANALYZE_PROMPT = """你是企业知识库 Agent 的路由器。根据用户问题和对话记忆，输出 JSON：

{
  "intent": "chitchat|fact_lookup|entity_relation|multi_hop|compare|summarize",
  "complexity": "simple|medium|complex",
  "needs_hybrid": true/false,
  "needs_graph": true/false,
  "needs_rewrite": true/false,
  "reasoning": "一句话说明路由理由"
}

规则：
1. 寒暄/感谢/与知识库无关 → intent=chitchat, needs_hybrid=false, needs_graph=false
2. 单个事实、定义、数值 → fact_lookup + simple，通常只需 hybrid
3. 问两个实体关系、组织架构 → entity_relation + medium，needs_graph=true
4. 「A 的 B 的 C」、跨文档推理 → multi_hop + complex，needs_rewrite=true, needs_graph=true
5. 对比/汇总类 → compare|summarize + complex，needs_rewrite=true
6. 有对话记忆且问题含「刚才/上面/它」→ needs_rewrite=true

只返回 JSON，不要 markdown。"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )


def _memory_hint(memory: MemoryContext | None) -> str:
    if not memory or not memory.has_content():
        return "（无对话记忆）"
    parts = []
    if memory.session_summary:
        parts.append(f"摘要: {memory.session_summary}")
    if memory.recent_turns:
        parts.append("最近: " + " | ".join(f"{t.role}:{t.content[:80]}" for t in memory.recent_turns[-3:]))
    return "\n".join(parts)


def _to_path(intent: Intent, complexity: Complexity, needs_hybrid: bool, needs_graph: bool) -> RoutePath:
    if intent == Intent.CHITCHAT or not needs_hybrid:
        return RoutePath.DIRECT
    if needs_graph and complexity == Complexity.COMPLEX:
        return RoutePath.FULL
    if needs_graph:
        return RoutePath.GRAPH
    return RoutePath.HYBRID


async def analyze_question(
    question: str,
    memory: MemoryContext | None = None,
) -> RouteDecision:
    # 拿到大模型对象
    llm = _get_llm()
    # 拼接给大模型看的输入文本：历史对话记忆 + 用户问题
    user_content = f"【对话记忆】\n{_memory_hint(memory)}\n\n【用户问题】\n{question}"

    # 异步调用大模型：系统提示词 + 用户组装好的内容
    resp = await llm.ainvoke([
        SystemMessage(content=ANALYZE_PROMPT),
        HumanMessage(content=user_content),
    ])

    # ------------------- 尝试解析大模型返回的JSON字符串 -------------------
    try:
        data = json.loads(resp.content.strip())
    except json.JSONDecodeError:
        return RouteDecision(
            intent=Intent.FACT_LOOKUP,
            complexity=Complexity.SIMPLE,
            path=RoutePath.HYBRID,
            needs_hybrid=True,
            needs_graph=False,
            needs_rewrite=False,
            reasoning="analyze JSON 解析失败，降级 hybrid",
        )

    try:
        intent = Intent(data.get("intent", "fact_lookup"))
        complexity = Complexity(data.get("complexity", "simple"))
    except ValueError:
        return RouteDecision(
            intent=Intent.FACT_LOOKUP,
            complexity=Complexity.SIMPLE,
            path=RoutePath.HYBRID,
            needs_hybrid=True,
            needs_graph=False,
            needs_rewrite=False,
            reasoning="analyze 枚举值非法，降级 hybrid",
        )

    needs_hybrid = bool(data.get("needs_hybrid", True))
    needs_graph = bool(data.get("needs_graph", False))
    needs_rewrite = bool(data.get("needs_rewrite", False))
    path = _to_path(intent, complexity, needs_hybrid, needs_graph)

    return RouteDecision(
        intent=intent,
        complexity=complexity,
        path=path,
        needs_hybrid=needs_hybrid,
        needs_graph=needs_graph,
        needs_rewrite=needs_rewrite,
        reasoning=data.get("reasoning", ""),
    )