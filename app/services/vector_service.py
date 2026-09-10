from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.es_client import delete_document_chunks, index_chunk
from app.infra.minio_client import download_file
from app.infra.neo4j_client import delete_document_graph
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.parsing.schemas import ParseStatus
from app.services.chunker import split_text
from app.ai.embeddings.embedder import embed_texts


async def _clear_existing_index(document_id: int, db: AsyncSession) -> None:
    """重复处理前先清理旧 chunks、ES 索引和图谱"""
    result = await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == document_id))
    for chunk in result.scalars().all():
        await db.delete(chunk)
    delete_document_chunks(document_id)
    delete_document_graph(document_id)


async def process_vector(document_id: int, db: AsyncSession) -> int:
    """解析 → 分块 → 写 PG + ES"""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ValueError(f"文档不存在: {document_id}")

    if doc.parse_status != ParseStatus.PARSED.value or not doc.parsed_markdown_key:
        raise ValueError(
            f"文档未解析完成: doc={document_id}, parse_status={doc.parse_status}, "
            f"parsed_markdown_key={doc.parsed_markdown_key}"
        )

    text = download_file(doc.parsed_markdown_key).decode("utf-8")
    if not text.strip():
        raise ValueError(f"解析结果为空: doc={document_id}")

    await _clear_existing_index(document_id, db)

    doc.vector_done = False
    doc.graph_done = False

    chunks = split_text(text)
    vectors = await embed_texts(chunks)

    for i, chunk_text in enumerate(chunks):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=chunk_text,
            embedding=vectors[i],
        )
        db.add(chunk)
        await db.flush()

        es_doc_id = index_chunk(
            chunk_id=chunk.id,
            document_id=doc.id,
            owner_id=doc.owner_id,
            title=doc.title,
            content=chunk_text,
            file_type=doc.file_type,
        )
        chunk.es_doc_id = es_doc_id

    doc.vector_done = True
    await db.flush()
    await db.refresh(doc)
    _maybe_mark_ready(doc)
    return len(chunks)


def _maybe_mark_ready(doc: Document) -> None:
    if doc.vector_done and doc.graph_done:
        doc.status = DocumentStatus.READY.value
