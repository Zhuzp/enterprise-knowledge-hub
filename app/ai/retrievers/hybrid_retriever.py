from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrievers.bm25_retriever import recall_bm25
from app.ai.retrievers.fusion import rrf_fuse
from app.ai.retrievers.pgvector_retriever import recall_pgvector
from app.ai.retrievers.reranker import rerank_hits
from app.ai.retrievers.schemas import ChunkHit
from app.core.settings import settings
from app.ai.retrievers.graph_retriever import recall_graph

#多路混合召回 
async def hybrid_retrieve(
    db: AsyncSession,
    question: str,
    owner_ids: list[int] | None,
    top_k: int | None = None,
) -> list[ChunkHit]:
    top_k = top_k or settings.rag_top_k #最终希望输出多少条 chunk
    recall_k = settings.recall_top_k #**召回阶段多拿一些候选，后面再过滤**。

    bm25_hits = recall_bm25(question, owner_ids, top_k=recall_k) #BM25 关键词检索 查出20条
    vector_hits = await recall_pgvector(db, question, owner_ids, top_k=recall_k) #PGVector 向量检索 查出20条
    graph_hits: list[ChunkHit] = []
    if settings.graph_recall_enabled:
        graph_hits = await recall_graph(db, question, owner_ids, top_k=recall_k)  # 新增

    #把两路召回结果列表交给 **RRF 倒数排名融合算法** 融合后取前10条
    fused = rrf_fuse(
        [bm25_hits, vector_hits, graph_hits],
        k=settings.rrf_k,
        top_n=max(settings.rrf_top_n, top_k),
    )

    reranked = await rerank_hits(question, fused, top_n=top_k) #Reranker 重排序 取前5条
    return reranked[:top_k]