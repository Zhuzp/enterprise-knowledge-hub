"""Agentic RAG：意图识别 → 条件路由 → 动态工具 → 生成"""

from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.ai.agents.analyze import analyze_question
from app.ai.agents.rewrite import rewrite_queries
from app.ai.agents.schemas import AgenticRAGState, RouteDecision, RoutePath
from app.ai.agents.tools import (
    chunks_to_context,
    merge_chunks,
    tool_graph_reason,
    tool_hybrid_search,
)
from app.ai.memory.prompt import SYSTEM_PROMPT, build_user_prompt
from app.ai.memory.schemas import MemoryContext
from app.core.settings import settings


# 拿到大模型对象，输出大模型实例
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
    )


# ── 节点 ──────────────────────────────────────────────
# 拿到用户问题，让大模型判断：这个问题该怎么处理。
async def analyze_node(state: AgenticRAGState) -> dict[str, Any]:
    decision = await analyze_question(
        state["question"],
        state.get("memory"),
    )
    return {"route_decision": decision}

# 把用户原始问题，改成更适合搜索的多个搜索词。
async def rewrite_node(state: AgenticRAGState) -> dict[str, Any]:
    decision = state["route_decision"]
    queries = await rewrite_queries(
        state["question"],
        state.get("memory"),
        graph_expand=decision.needs_graph if decision else False,
    )
    return {"rewritten_queries": queries}

# 去知识库检索文档片段 chunks（BM25 + 向量；图谱由 graph_node 单独处理）。
async def hybrid_node(state: AgenticRAGState) -> dict[str, Any]:
    queries = state.get("rewritten_queries") or [state["question"]]
    chunks = await tool_hybrid_search(queries, state["owner_ids"])
    return {"chunks": chunks}

# **专门处理关系类问题，调用 Neo4j 知识图谱。**
async def graph_node(state: AgenticRAGState) -> dict[str, Any]:
    query = (state.get("rewritten_queries") or [state["question"]])[0]
    reasoning, graph_chunks = await tool_graph_reason(query, state["owner_ids"])

    existing = state.get("chunks") or []
    merged = merge_chunks(existing, graph_chunks)
    context = chunks_to_context(merged, graph_reasoning=reasoning)

    return {
        "graph_reasoning": reasoning,
        "chunks": merged,
        "context": context,
    }

# 把检索出来的 chunks、图谱推理文本，拼接成一大段字符串 context，给大模型看。
async def merge_node(state: AgenticRAGState) -> dict[str, Any]:
    """hybrid 已有 chunks、graph 未跑时，在此合并 context"""
    chunks = state.get("chunks") or []
    reasoning = state.get("graph_reasoning") or ""
    context = chunks_to_context(chunks, graph_reasoning=reasoning)
    return {"context": context}

# 把上下文、用户问题、历史记忆丢给大模型，产出最终回答 answer。
async def generate_node(state: AgenticRAGState) -> dict[str, Any]:
    memory = state.get("memory") or MemoryContext()
    decision = state.get("route_decision")

    # direct 路径：无检索，靠记忆/模型常识
    if decision and decision.path.value == "direct":
        if not memory.has_content():
            return {"answer": "你好！我是企业知识库助手，请上传资料或直接提问业务问题。"}
        user_prompt = build_user_prompt(
            question=state["question"],
            rag_context="",
            memory=memory,
        )
    else:
        if not state.get("context") and not memory.has_content():
            return {"answer": "未找到相关文档，请先上传资料后再提问。"}
        user_prompt = build_user_prompt(
            question=state["question"],
            rag_context=state.get("context", ""),
            memory=memory,
        )

    llm = _get_llm()
    resp = await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    return {"answer": resp.content}


# ── 条件路由 ──────────────────────────────────────────

def route_after_analyze(state: AgenticRAGState) -> Literal["direct", "rewrite_hybrid", "rewrite_full", "hybrid_only"]:
    path = state["route_decision"].path
    if path == RoutePath.DIRECT:
        return "direct"
    if path == RoutePath.FULL:
        return "rewrite_full"
    if path == RoutePath.GRAPH:
        return "rewrite_full"   # graph 路径也先 rewrite
    return "rewrite_hybrid" if state["route_decision"].needs_rewrite else "hybrid_only"


def route_after_hybrid(state: AgenticRAGState) -> Literal["graph", "merge"]:
    if state["route_decision"].needs_graph:
        return "graph"
    return "merge"


# ── 构图 ──────────────────────────────────────────────

def build_agentic_rag_graph():
    # 1. 创建一张空的图，指定整张图共用的状态容器 AgenticRAGState
    graph = StateGraph(AgenticRAGState)  # type: ignore[bad-specialization]

    # 2. add_node：把一个个函数注册成图里面的“步骤（节点）”，给每个步骤起个名字
    graph.add_node("analyze", analyze_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("hybrid", hybrid_node)
    graph.add_node("graph", graph_node)
    graph.add_node("merge", merge_node)
    graph.add_node("generate", generate_node)

    # 3. add_edge：普通连线，固定顺序，A执行完直接去B
    graph.add_edge(START, "analyze")

    # 4. add_conditional_edges：条件分支连线 —— 路口，根据函数返回值选择下一站去哪里
    graph.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {
            "direct": "generate",
            "hybrid_only": "hybrid",
            "rewrite_hybrid": "rewrite",
            "rewrite_full": "rewrite",
        },
    )

    # rewrite跑完固定去hybrid
    graph.add_edge("rewrite", "hybrid")

    # hybrid执行完之后的第二个路口
    graph.add_conditional_edges(
        "hybrid",
        route_after_hybrid,
        {
            "graph": "graph",
            "merge": "merge",
        },
    )

    # graph节点跑完直接去generate
    graph.add_edge("graph", "generate")
    # merge节点跑完直接去generate
    graph.add_edge("merge", "generate")
    # generate执行完毕，整个流程结束 END
    graph.add_edge("generate", END)

    # compile：编译，把上面所有配置打包，返回一个可以ainvoke执行的图实例
    return graph.compile()


agentic_rag_graph = build_agentic_rag_graph()


def _needs_rewrite(decision) -> bool:
    if decision.path in (RoutePath.FULL, RoutePath.GRAPH):
        return True
    return decision.needs_rewrite


async def run_agentic_retrieve(
    question: str,
    owner_ids: list[int] | None,
    memory: MemoryContext | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], RouteDecision]:
    """与 LangGraph 相同的检索路由，供流式/非流式共用。"""
    memory = memory or MemoryContext()
    decision = await analyze_question(question, memory)
    meta: dict[str, Any] = {"route": decision.model_dump()}

    if decision.path == RoutePath.DIRECT:
        return "", [], meta, decision

    queries = [question]
    if _needs_rewrite(decision):
        queries = await rewrite_queries(
            question,
            memory,
            graph_expand=decision.needs_graph,
        )
        meta["rewritten_queries"] = queries

    chunks = await tool_hybrid_search(queries, owner_ids)

    if decision.needs_graph:
        reasoning, graph_chunks = await tool_graph_reason(queries[0], owner_ids)
        chunks = merge_chunks(chunks, graph_chunks)
        context = chunks_to_context(chunks, graph_reasoning=reasoning)
        meta["graph_reasoning"] = reasoning
    else:
        context = chunks_to_context(chunks)

    return context, chunks, meta, decision


def _build_meta(result: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if d := result.get("route_decision"):
        meta["route"] = d.model_dump()
    if rq := result.get("rewritten_queries"):
        meta["rewritten_queries"] = rq
    if gr := result.get("graph_reasoning"):
        meta["graph_reasoning"] = gr
    return meta


async def run_agentic_rag(
    question: str,
    owner_ids: list[int] | None,
    memory: MemoryContext | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    # **异步执行整个 LangGraph 图，把输入丢进去，跑完把完整最终状态返回出来**。
    result = await agentic_rag_graph.ainvoke({
        "question": question,
        "owner_ids": owner_ids,
        "memory": memory,
    })
    return result["answer"], result.get("chunks", []), _build_meta(result)