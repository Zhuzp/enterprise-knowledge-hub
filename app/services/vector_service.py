from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.es_client import delete_document_chunks, index_chunk
from app.infra.minio_client import download_file
from app.infra.neo4j_client import delete_document_graph
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.chunker import split_text
from app.services.parser import parse_document
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
    # 查询文档主记录
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ValueError(f"文档不存在: {document_id}")

    # 清理旧分块、ES、Neo4j旧数据
    await _clear_existing_index(document_id, db)

    # 重置两个完成标记
    doc.vector_done = False
    doc.graph_done = False

    # 1.从MinIO下载原始文件字节流
    file_data = download_file(doc.minio_key)
    # 2.文档解析：pdf/docx/txt → 提取纯文本
    text = parse_document(file_data, doc.file_type)

    # 解析完是空文本，标记失败，返回0个块
    if not text.strip():
        doc.status = DocumentStatus.FAILED.value
        return 0

    # 3.文本分块
    chunks = split_text(text)
    # 4.批量向量化，得到每个chunk的embedding向量数组
    vectors = await embed_texts(chunks)

    # 循环每一个文本块
    for i, chunk_text in enumerate(chunks):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=chunk_text,
            embedding=vectors[i],
        )
        db.add(chunk)
        await db.flush() # flush：立刻拿到chunk自增id，但不commit提交事务

        # 写入ES向量库，返回ES文档id
        es_doc_id = index_chunk(
            chunk_id=chunk.id,
            document_id=doc.id,
            owner_id=doc.owner_id,
            title=doc.title,
            content=chunk_text,
            file_type=doc.file_type,
        )
        chunk.es_doc_id = es_doc_id #回填ES的id到PG分块记录

    doc.vector_done = True
    await db.flush()
    await db.refresh(doc)
    # 判断向量、图谱两者都完成，文档状态置 READY  
    _maybe_mark_ready(doc)
    return len(chunks)


def _maybe_mark_ready(doc: Document) -> None:
    if doc.vector_done and doc.graph_done:
        doc.status = DocumentStatus.READY.value
