"""LangGraph RAG 工作流：检索 → 生成"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import NotRequired, TypedDict

from app.ai.retrievers.hybrid_retriever import hybrid_retrieve
from app.core.settings import settings
from app.infra.db import AsyncSessionLocal
from app.ai.memory.prompt import SYSTEM_PROMPT, build_user_prompt
from app.ai.memory.schemas import MemoryContext


SYSTEM_PROMPT = """你是企业内部知识库助手。请仅根据提供的参考资料回答问题。
如果参考资料中没有相关信息，请明确说「根据现有资料无法回答」，不要编造。
回答请简洁、准确，使用中文。"""


class RAGState(TypedDict):
    question: str
    owner_ids: list[int] | None
    memory: NotRequired[MemoryContext | None]   # 新增
    context: NotRequired[str]
    answer: NotRequired[str]
    chunks: NotRequired[list[dict[str, Any]]]


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
    )


async def _do_retrieve(question: str, owner_ids: list[int] | None) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        hits = await hybrid_retrieve(db, question, owner_ids, settings.rag_top_k)
        return [h.to_dict() for h in hits]


async def retrieve_node(state: RAGState) -> dict[str, Any]:
    chunks = await _do_retrieve(state["question"], state["owner_ids"])
    memory = state.get("memory") or MemoryContext()

    if not chunks:
        if memory.has_content():
            return {"chunks": [], "context": ""}  # 交给 generate，靠记忆答
        return {
            "chunks": [],
            "context": "",
            "answer": "未找到相关文档，请先上传资料后再提问。",
        }

    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] 文档《{c['title']}》\n{c['content']}")
    context = "\n\n".join(parts)
    return {"chunks": chunks, "context": context}


async def generate_node(state: RAGState) -> dict[str, Any]:
    if not state.get("context") and not state.get("memory", MemoryContext()).has_content():
        # 无资料且无记忆时的兜底（retrieve 已处理无 chunk 情况）
        if state.get("answer"):
            return {"answer": state["answer"]}
        return {"answer": "未找到相关文档，请先上传资料后再提问。"}
    memory = state.get("memory") or MemoryContext()
    user_prompt = build_user_prompt(
        question=state["question"],
        rag_context=state.get("context", ""),
        memory=memory,
    )

    llm = _get_llm()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]
    response = await llm.ainvoke(messages)
    return {"answer": response.content}


def build_rag_graph():
    # Pyrefly 已知误报：https://github.com/facebook/pyrefly/issues/3745
    graph = StateGraph(RAGState)  # type: ignore[bad-specialization]
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


rag_graph = build_rag_graph()


async def run_rag(
    question: str,
    owner_ids: list[int] | None,
    memory: MemoryContext | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    result = await rag_graph.ainvoke({
        "question": question,
        "owner_ids": owner_ids,
        "memory": memory,
    })
    return result["answer"], result.get("chunks", [])
