"""上传后解析：raw → Markdown → MinIO"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.minio_client import download_file, upload_file
from app.models.document import Document
from app.parsing.pipeline import parse_to_markdown  # 前面设计的统一入口
from app.parsing.schemas import ParseStatus

logger = logging.getLogger(__name__)


async def _update_parse_progress(db, doc, progress: float, stage: str):
    """更新解析进度元数据，flush到数据库（不commit）"""
    meta = dict(doc.parse_metadata or {})
    meta["progress"] = round(progress, 2)
    meta["stage"] = stage
    doc.parse_metadata = meta
    await db.flush()

async def run_document_parse(document_id: int, db: AsyncSession) -> None:
    # 查询文档记录
    doc = await db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"文档不存在: {document_id}")

    # 幂等：已经解析完成直接返回
    if doc.parse_status == ParseStatus.PARSED.value:
        logger.info("已解析，跳过 doc=%s", document_id)
        return

    # 修改状态为【解析中】，flush刷新到数据库事务缓冲区
    doc.parse_status = ParseStatus.PARSING.value
    doc.parse_error = None
    await db.flush()

    try:
        # 1. 从MinIO下载原始文件二进制
        raw_bytes = download_file(doc.minio_key)
        # 生成文档唯一标识，用于内部资源、图片assets命名
        doc_uuid = f"doc_{doc.id}_{uuid.uuid4().hex[:8]}"

        # 进度回调函数：解析流水线内部会回调，实时更新进度百分比、当前阶段
        async def progress_callback(ratio: float, stage: str) -> None:
            """
            ratio: 0.0 ~ 1.0，表示整体进度
            stage: 当前阶段描述，如 "segment 2/5"
            """
            await _update_parse_progress(db, doc, ratio, stage)

        # 2. 调用解析流水线核心入口
        result = await parse_to_markdown(
            file_data=raw_bytes,
            file_type=doc.file_type,
            file_name=doc.file_name,
            owner_id=doc.owner_id,
            document_id=doc.id,
            doc_uuid=doc_uuid,
            progress_callback=progress_callback,
        )

        # 校验：解析出来markdown为空，直接抛异常标记失败
        if not result.markdown.strip():
            raise ValueError("解析结果为空")

        # 3. 回填数据库：解析后的markdown已经在parse_to_markdown内部上传MinIO
        doc.parsed_markdown_key = result.markdown_key
        doc.parse_metadata = result.metadata
        doc.parse_status = ParseStatus.PARSED.value

        # 可选：写 document_assets 表
        # await save_assets(db, doc.id, result.assets)

        await db.flush()
        logger.info("解析完成 doc=%s md_key=%s", document_id, result.markdown_key)

    except Exception as exc:
        logger.exception("解析失败 doc=%s", document_id)
        doc.parse_status = ParseStatus.FAILED.value
        doc.parse_error = str(exc)[:500]
        await db.flush()
        raise