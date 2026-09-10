import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graph.entity_extractor import extract_and_store
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.vector_service import _maybe_mark_ready


async def process_graph(document_id: int, db: AsyncSession, max_retry: int = 10) -> int:
    """从 PG 读 chunks → 写 Neo4j（等 vector consumer 写完 chunks）"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ValueError(f"文档不存在: {document_id}")

    for attempt in range(max_retry):
        chunk_result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunks = chunk_result.scalars().all()
        if chunks:
            break
        await asyncio.sleep(2**attempt)
    else:
        raise RuntimeError(f"等待 chunks 超时: document_id={document_id}")

    count = 0
    for chunk in chunks:
        extract_and_store(
            chunk_id=chunk.id,
            document_id=doc.id,
            title=doc.title,
            content=chunk.content,
            owner_id=doc.owner_id,
        )
        count += 1

    doc.graph_done = True
    await db.flush()
    await db.refresh(doc)
    _maybe_mark_ready(doc)
    return count
