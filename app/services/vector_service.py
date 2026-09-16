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
    # 1. 查询文档主记录
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ValueError(f"文档不存在: {document_id}")
    # 校验前置条件：必须已经解析完成、有markdown文件
    if doc.parse_status != ParseStatus.PARSED.value or not doc.parsed_markdown_key:
        raise ValueError(
            f"文档未解析完成: doc={document_id}, parse_status={doc.parse_status}, "
            f"parsed_markdown_key={doc.parsed_markdown_key}"
        )
    # 2. 从对象存储下载解析后的markdown文本
    text = download_file(doc.parsed_markdown_key).decode("utf-8")
    if not text.strip():
        raise ValueError(f"解析结果为空: doc={document_id}")

    # 3. 清理此文档旧的chunk向量、ES索引（重跑向量化时用）
    await _clear_existing_index(document_id, db)
    # 标记向量、图谱任务未完成
    doc.vector_done = False
    doc.graph_done = False

    # 4. 文本分块 + 调用你前面写的embed_texts批量生成向量
    chunks = split_text(text)
    vectors = await embed_texts(chunks)

    # 5. 循环：每一个chunk写入PG，同时写入ES全文索引
    for i, chunk_text in enumerate(chunks):
        chunk = DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            content=chunk_text,
            embedding=vectors[i],
        )
        db.add(chunk)
        await db.flush()
        # 同步写入ES，用于关键词检索
        es_doc_id = index_chunk(
            chunk_id=chunk.id,
            document_id=doc.id,
            owner_id=doc.owner_id,
            title=doc.title,
            content=chunk_text,
            file_type=doc.file_type,
        )
        chunk.es_doc_id = es_doc_id

    # 全部chunk处理完，更新文档状态
    doc.vector_done = True
    await db.flush()
    await db.refresh(doc)
    _maybe_mark_ready(doc)# 文档整体就绪钩子
    return len(chunks)


def _maybe_mark_ready(doc: Document) -> None:
    if doc.vector_done and doc.graph_done:
        doc.status = DocumentStatus.READY.value
