"""查询重写：消歧、拆分子问题、图谱扩展"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.ai.graph.graph_retriever import expand_entities_from_question
from app.ai.memory.schemas import MemoryContext
from app.core.settings import settings

# 系统提示词：告诉大模型做什么，输出格式要求
REWRITE_PROMPT = """你是检索 query 优化器。根据对话记忆，将用户问题改写为 1~3 条独立、可检索的搜索 query。

输出 JSON：
{"queries": ["query1", "query2"]}

要求：
- 补全指代（「它」「刚才那个流程」）
- 复杂对比题拆成多条
- 每条 query 自洽，不依赖上下文
- 不要编造实体名

只返回 JSON。""" 


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )


async def rewrite_queries(
    question: str,
    memory: MemoryContext | None = None,
    *,
    graph_expand: bool = False,
) -> list[str]:
    llm = _get_llm()
    # 提取最近最多5轮对话记忆文本
    memory_text = ""
    if memory and memory.recent_turns:
        memory_text = "\n".join(f"{t.role}: {t.content}" for t in memory.recent_turns[-5:])

    # 调用大模型，传入改写prompt + 记忆 + 用户问题
    resp = await llm.ainvoke([
        SystemMessage(content=REWRITE_PROMPT),
        HumanMessage(content=f"【记忆】\n{memory_text}\n\n【问题】\n{question}"),
    ])

    # 兜底：解析失败就直接用原始问题作为唯一query
    queries = [question]
    try:
        data = json.loads(resp.content.strip())
        # 校验queries是数组且不为空，最多取3条
        if isinstance(data.get("queries"), list) and data["queries"]:
            queries = [str(q) for q in data["queries"][:3]]
    except json.JSONDecodeError:
        # LLM输出JSON格式错误，直接pass，保留兜底 queries = [question]
        pass

    # 如果开启 graph_expand：做图谱实体扩展
    if graph_expand:
        expanded: list[str] = []
        for q in queries:
            # expand_entities_from_question：从query抽取关联实体（从知识图谱）
            related = expand_entities_from_question(q)
            # 把原query拼接上关联实体，生成扩展后的搜索词
            expanded.append(q + (" " + " ".join(related) if related else ""))
        queries = expanded

    # 字符串去重，保持顺序，过滤空字符串
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    # 极端情况全部过滤空了，兜底返回原始问题
    return out or [question]