from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin
from app.infra.db import get_db
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.schemas.document import DocumentListResponse, DocumentResponse, DocumentReviewRequest, DocumentReviewResponse
from app.services.review_service import review_document

router = APIRouter()


@router.get("/pending", response_model=DocumentListResponse)
async def list_pending_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    base = select(Document).where(Document.status == DocumentStatus.PENDING_REVIEW.value)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    offset = (page - 1) * page_size
    items = (
        await db.execute(base.order_by(Document.created_at.asc()).offset(offset).limit(page_size))
    ).scalars().all()
    return DocumentListResponse(total=total, items=items)


@router.post("/{doc_id}", response_model=DocumentReviewResponse)
async def review_one_document(
    doc_id: int,
    data: DocumentReviewRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, detail="文档不存在")

    if data.action == "reject" and not data.reason:
        raise HTTPException(400, detail="拒绝时必须填写 reason")

    try:
        doc = await review_document(db, doc, admin.id, data.action, data.reason)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))

    msg = "审核通过，已投递处理队列" if data.action == "approve" else "已拒绝"
    return DocumentReviewResponse(message=msg, document=doc)