from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.services.graph_service import process_graph
from app.services.vector_service import process_vector


async def reindex_document(document_id: int, db: AsyncSession) -> int:
    """重新索引：清理旧数据后同步执行向量 + 图谱处理"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ValueError(f"文档不存在: {document_id}")

    doc.status = DocumentStatus.PROCESSING.value
    doc.vector_done = False
    doc.graph_done = False
    await db.flush()

    chunk_count = await process_vector(document_id, db)
    await process_graph(document_id, db)
    return chunk_count
