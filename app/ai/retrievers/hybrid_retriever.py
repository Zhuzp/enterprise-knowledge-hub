from contextlib import nullcontext

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrievers.bm25_retriever import recall_bm25
from app.ai.retrievers.fusion import rrf_fuse
from app.ai.retrievers.pgvector_retriever import recall_pgvector
from app.ai.retrievers.reranker import rerank_hits
from app.ai.retrievers.schemas import ChunkHit
from app.core.settings import settings
from app.models.document import Document, DocumentStatus


async def _filter_ready_hits(
    db: AsyncSession,
    hits: list[ChunkHit],
) -> list[ChunkHit]:
    if not hits:
        return hits
    doc_ids = {h.document_id for h in hits}
    ready_ids = set(
        (
            await db.execute(
                select(Document.id).where(
                    Document.id.in_(doc_ids),
                    Document.status == DocumentStatus.READY.value,
                )
            )
        ).scalars().all()
    )
    return [h for h in hits if h.document_id in ready_ids]


async def hybrid_retrieve(
    db: AsyncSession,
    question: str,
    owner_ids: list[int] | None,
    top_k: int | None = None,
) -> list[ChunkHit]:
    """BM25 + 向量混合召回。图谱检索由 LangGraph graph_node 单独负责。"""
    top_k = top_k or settings.rag_top_k
    recall_k = settings.recall_top_k

    from app.observability import is_langfuse_enabled

    span_cm: nullcontext | object = nullcontext()
    if is_langfuse_enabled():
        try:
            from langfuse import get_client

            span_cm = get_client().start_as_current_observation(
                as_type="span", name="retrieve.hybrid"
            )
        except Exception:
            span_cm = nullcontext()

    with span_cm as span:
        bm25_hits = await _filter_ready_hits(
            db, recall_bm25(question, owner_ids, top_k=recall_k)
        )
        vector_hits = await recall_pgvector(db, question, owner_ids, top_k=recall_k)

        fused = rrf_fuse(
            [bm25_hits, vector_hits],
            k=settings.rrf_k,
            top_n=max(settings.rrf_top_n, top_k),
        )

        reranked = await rerank_hits(question, fused, top_n=top_k)
        result = reranked[:top_k]

        if span is not None:
            try:
                def _ids(hits: list[ChunkHit]) -> list[int]:
                    return [h.chunk_id for h in hits]

                span.update(
                    input={"question": question[:500]},
                    output={
                        "bm25_ids": _ids(bm25_hits),
                        "vector_ids": _ids(vector_hits),
                        "rrf_ids": _ids(fused),
                        "rerank_ids": _ids(result),
                        "counts": {
                            "bm25": len(bm25_hits),
                            "vector": len(vector_hits),
                            "final": len(result),
                        },
                    },
                )
            except Exception:
                pass

    return result
