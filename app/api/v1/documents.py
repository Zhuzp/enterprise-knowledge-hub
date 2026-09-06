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
from app.models.document import Document, DocumentStatus, DocumentVisibility
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.schemas.document import DocumentListResponse, DocumentResponse, DocumentUpdateRequest, DocumentUploadResponse
from app.services.audit_service import write_audit_log
from app.services.permission_service import get_document_filter, is_admin
from app.infra.neo4j_client import delete_document_graph

router = APIRouter()

# 文件类型 → MIME 映射
CONTENT_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
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

    # 检查大小
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制（最大 {settings.max_upload_size_mb}MB）",
        )

    # 上传到 MinIO
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
            visibility=visibility,
            department_id=department_id,
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        await write_audit_log(db, current_user.id, "upload", "document", doc.id, doc.title)
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
