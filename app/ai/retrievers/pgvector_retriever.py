from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.embedder import embed_text
from app.ai.retrievers.schemas import ChunkHit
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk


async def recall_pgvector(
    db: AsyncSession,
    query: str,
    owner_ids: list[int] | None,
    top_k: int = 20,
) -> list[ChunkHit]:
    # 1.用户问题文本 -> 向量
    query_vec = await embed_text(query)

    # 2. SQLAlchemy 构建查询语句
    stmt = (
        select(
            DocumentChunk,
            Document.title,
        )
        # 关联文档表，拿文档标题
        .join(Document, Document.id == DocumentChunk.document_id)
        # 只取【已经处理完成、就绪的文档】
        .where(Document.status == DocumentStatus.READY.value)
        # 过滤掉还没生成向量的chunk
        .where(DocumentChunk.embedding.is_not(None))
        # 按余弦距离从小到大排序：距离越小，语义越相似
        .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
        .limit(top_k)
    )
    # 权限过滤：如果传入owner_ids，只查询这些用户名下文档（多租户）
    if owner_ids is not None:
        stmt = stmt.where(Document.owner_id.in_(owner_ids))

    # 3. 执行SQL
    rows = (await db.execute(stmt)).all()

    # 4. 封装成统一返回结构体 ChunkHit
    results: list[ChunkHit] = []
    for rank, (chunk, title) in enumerate(rows, start=1):
        results.append(
            ChunkHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=title,
                content=chunk.content,
                score=1.0 / rank,  # RRF 只用 rank，这里占位
                source="pgvector",
                rank=rank,
            )
        )
    return results