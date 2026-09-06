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
    query_vec = await embed_text(query)

    stmt = (
        select(
            DocumentChunk,
            Document.title,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.status == DocumentStatus.READY.value)
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
        .limit(top_k)
    )
    if owner_ids is not None:
        stmt = stmt.where(Document.owner_id.in_(owner_ids))

    rows = (await db.execute(stmt)).all()

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