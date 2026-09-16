"""Agent 可调用的检索工具（封装现有 retriever）"""

from app.ai.agents.graph_reason import graph_reason
from app.ai.retrievers.hybrid_retriever import hybrid_retrieve
from app.ai.retrievers.schemas import ChunkHit
from app.core.settings import settings
from app.infra.db import AsyncSessionLocal


async def tool_hybrid_search(
    queries: list[str],
    owner_ids: list[int] | None,
) -> list[dict]:
    """多 query 文本混合检索（BM25 + 向量），结果去重"""
    all_hits: list[ChunkHit] = []
    seen: set[int] = set()

    async with AsyncSessionLocal() as db:
        for q in queries:
            hits = await hybrid_retrieve(db, q, owner_ids, settings.rag_top_k)

            for h in hits:
                if h.chunk_id in seen:
                    continue
                seen.add(h.chunk_id)
                all_hits.append(h)

    return [h.to_dict() for h in all_hits[: settings.rag_top_k]]


async def tool_graph_reason(
    question: str,
    owner_ids: list[int] | None,
) -> tuple[str, list[dict]]:
    async with AsyncSessionLocal() as db:
        result = await graph_reason(db, question, owner_ids, settings.rag_top_k)
    return result.reasoning_text, [h.to_dict() for h in result.chunk_hits]


def merge_chunks(*chunk_lists: list[dict]) -> list[dict]:
    seen: set[int] = set()
    merged: list[dict] = []
    for lst in chunk_lists:
        for c in lst:
            cid = c["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            merged.append(c)
    return merged


def chunks_to_context(chunks: list[dict], graph_reasoning: str = "") -> str:
    parts: list[str] = []
    if graph_reasoning:
        parts.append(graph_reasoning)
    for i, c in enumerate(chunks, 1):
        src = c.get("source", "hybrid")
        parts.append(f"[{i}] ({src}) 文档《{c['title']}》\n{c['content']}")
    return "\n\n".join(parts)