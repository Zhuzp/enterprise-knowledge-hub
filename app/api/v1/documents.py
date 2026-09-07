import os
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.settings import settings
from app.infra.db import get_db
from app.infra.es_client import delete_document_chunks
from app.infra.minio_client import delete_file, download_file, generate_object_key, upload_file
from app.infra.rabbitmq_client import publish_document_uploaded
from app.models.document import Document, DocumentStatus, DocumentVisibility, ParseStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdateRequest,
    DocumentUploadResponse,
    ParsedPreviewResponse,
)
from app.services.audit_service import write_audit_log
from app.services.permission_service import get_document_filter, is_admin
from app.infra.neo4j_client import delete_document_graph
from app.parsing.registry import infer_media_category

router = APIRouter()

# 文件类型 → MIME 映射
CONTENT_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


def validate_file(file: UploadFile) -> tuple[str, str, str]:
    """校验文件类型，返回 (扩展名, 文件类型, 文件名)"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    filename = file.filename
    _, ext = os.path.splitext(filename.lower())
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，允许: {settings.allowed_file_types}",
        )

    file_type = ext.lstrip(".")  # ".pdf" → "pdf"
    return ext, file_type, filename


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(..., description="上传的文件，字段名必须是 file"),
    title: str | None = Form(None, description="文档标题，可选"),
    visibility: str = Form("private"),  # 新增
    department_id: int | None = Form(None),  # 新增
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext, file_type, filename = validate_file(file)

    # visibility 校验
    if visibility not in {v.value for v in DocumentVisibility}:
        raise HTTPException(400, detail="visibility 只能是 private / department / public")
    if visibility == DocumentVisibility.DEPARTMENT.value and department_id is None:
        # 部门可见必须指定部门；默认用当前用户部门
        department_id = current_user.department_id
        if department_id is None:
            raise HTTPException(400, detail="部门可见文档需要指定 department_id 或加入部门")

    # 读取文件内容
    file_data = await file.read()
    file_size = len(file_data)

    # 文档 / 音视频 大小分级
    is_media = infer_media_category(file_type) in {"audio", "video"}
    max_mb = settings.max_media_upload_size_mb if is_media else settings.max_upload_size_mb
    if file_size > max_mb * 1024 * 1024:
        raise HTTPException(400, detail=f"文件超过 {max_mb}MB 限制")
    object_key = generate_object_key(current_user.id, filename)
    content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")

    try:
        upload_file(file_data, object_key, content_type)

        # 写入数据库
        doc = Document(
            title=title or filename,
            file_name=filename,
            file_size=file_size,
            file_type=file_type,
            minio_key=object_key,
            owner_id=current_user.id,
            status=DocumentStatus.PENDING_REVIEW.value,
            parse_status=ParseStatus.PENDING.value,
            media_category=infer_media_category(file_type),
            visibility=visibility,
            department_id=department_id,
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        await write_audit_log(db, current_user.id, "upload", "document", doc.id, doc.title)

         # ★ 上传后立即投递解析任务（不阻塞 HTTP）
        await publish_document_uploaded(doc.id, doc.file_type)
    except Exception:
        delete_file(object_key)  # 失败清理 MinIO
        raise
    return DocumentUploadResponse(document=doc)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    admin = await is_admin(db, current_user.id)
    doc_filter = await get_document_filter(current_user, admin)

    base = select(Document)
    if doc_filter is not True:
        base = base.where(doc_filter)

    # 查总数
    count_result = await db.execute(select(func.count()).select_from(base.subquery()))

    total = count_result.scalar() or 0

    # 查分页数据
    offset = (page - 1) * page_size
    result = await db.execute(base.order_by(Document.created_at.desc()).offset(offset).limit(page_size))
    items = result.scalars().all()

    return DocumentListResponse(total=total, items=items)


async def _get_accessible_document(
    db: AsyncSession,
    doc_id: int,
    user: User,
) -> Document:
    admin = await is_admin(db, user.id)
    doc_filter = await get_document_filter(user, admin)
    stmt = select(Document).where(Document.id == doc_id)
    if doc_filter is not True:
        stmt = stmt.where(doc_filter)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_accessible_document(db, doc_id, current_user)


@router.get("/{doc_id}/parsed", response_model=ParsedPreviewResponse)
async def get_parsed_preview(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看解析结果 Markdown（审核前预览 / 排查失败）"""
    # 校验：文档存在 + 当前用户有权访问该文档
    doc = await _get_accessible_document(db, doc_id, current_user)
    # 公共基础返回字段
    base = {
        "document_id": doc.id,
        "file_name": doc.file_name,
        "media_category": doc.media_category,
        "metadata": doc.parse_metadata,
    }
    # 状态分支：待解析
    if doc.parse_status == ParseStatus.PENDING.value:
        return ParsedPreviewResponse(status="pending", **base)
    # 状态分支：解析中，metadata里面带着progress、stage给前端展示进度条
    if doc.parse_status == ParseStatus.PARSING.value:
        return ParsedPreviewResponse(status="parsing", **base)
    # 状态分支：解析失败，把数据库存的parse_error返回前端展示
    if doc.parse_status == ParseStatus.FAILED.value:
        return ParsedPreviewResponse(status="failed", error=doc.parse_error or "解析失败", **base)
    # 异常兜底：状态不是PARSED，或者markdown的minio_key为空
    if doc.parse_status != ParseStatus.PARSED.value or not doc.parsed_markdown_key:
        return ParsedPreviewResponse(status="unknown", error="缺少 parsed markdown", **base)

    # 真正读取MinIO里面已经解析好的content.md
    try:
        markdown = download_file(doc.parsed_markdown_key).decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取解析结果失败: {exc}") from exc

    return ParsedPreviewResponse(status="parsed", markdown=markdown, **base)


@router.post("/{doc_id}/reparse", response_model=DocumentUploadResponse)
async def reparse_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解析失败或需重跑时，重新投递 parse 队列"""
    # 权限校验：能访问文档
    doc = await _get_accessible_document(db, doc_id, current_user)
    # 权限二次校验：只能重跑自己文档，管理员除外
    if doc.owner_id != current_user.id and not await is_admin(db, current_user.id):
        raise HTTPException(status_code=403, detail="只能重新解析自己的文档")
    # 冲突：正在解析，不允许重复提交
    if doc.parse_status == ParseStatus.PARSING.value:
        raise HTTPException(status_code=409, detail="文档正在解析中，请稍后再试")

    # 重置数据库字段，回到待解析状态
    doc.parse_status = ParseStatus.PENDING.value
    doc.parse_error = None
    doc.parsed_markdown_key = None
    doc.parse_metadata = {"progress": 0.0, "stage": "reparse_queued"}
    await db.flush()
    await db.refresh(doc)

    # 核心：发布MQ消息，和上传新文件走完全一模一样的流程
    await publish_document_uploaded(doc.id, doc.file_type)
    # 写审计日志，记录谁触发了重解析
    await write_audit_log(db, current_user.id, "reparse", "document", doc.id, doc.title)
    return DocumentUploadResponse(message="已重新提交解析", document=doc)


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_accessible_document(db, doc_id, current_user)

    # 最好改成异步调用，防止阻塞主进程
    file_data = download_file(doc.minio_key)
    content_type = CONTENT_TYPE_MAP.get(f".{doc.file_type}", "application/octet-stream")

    return StreamingResponse(
        BytesIO(file_data),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.file_name}"'},
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_accessible_document(db, doc_id, current_user)
    # 只有 owner 或 admin 能删 — 额外校验：
    if doc.owner_id != current_user.id and not await is_admin(db, current_user.id):
        raise HTTPException(403, detail="只能删除自己的文档")

    # 删 MinIO 文件
    delete_file(doc.minio_key)
    # 删 ES 索引
    delete_document_chunks(doc.id)
    # 删 Neo4j 图谱
    delete_document_graph(doc.id)
    # 删 chunk 记录
    chunk_result = await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    for chunk in chunk_result.scalars().all():
        await db.delete(chunk)
    # 删文档记录
    await db.delete(doc)
    await write_audit_log(db, current_user.id, "delete", "document", doc.id)


@router.patch("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    data: DocumentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await _get_accessible_document(db, doc_id, current_user)
    if doc.owner_id != current_user.id and not await is_admin(db, current_user.id):
        raise HTTPException(403, detail="只能修改自己的文档")

    if data.visibility is not None:
        doc.visibility = data.visibility
    if data.department_id is not None:
        doc.department_id = data.department_id

    await db.flush()
    await db.refresh(doc)
    return doc

