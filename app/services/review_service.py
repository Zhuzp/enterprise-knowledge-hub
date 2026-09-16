from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.infra.rabbitmq_client import publish_document_published
from app.models.document import Document, DocumentStatus, ParseStatus
from app.services.audit_service import write_audit_log


def _ensure_parse_ready_for_approve(doc: Document) -> None:
    """审核通过前：必须已完成解析且存在 Markdown 产物"""
    if not settings.review_require_parsed:
        return

    if doc.parse_status == ParseStatus.PARSING.value:
        raise ValueError("文档仍在解析中，请稍后再审核")

    if doc.parse_status == ParseStatus.PENDING.value:
        raise ValueError("文档尚未开始解析或 parse worker 未运行，请稍后再审核")

    if doc.parse_status == ParseStatus.FAILED.value:
        raise ValueError(f"文档解析失败，无法通过审核：{doc.parse_error or '未知错误'}")

    if doc.parse_status != ParseStatus.PARSED.value or not doc.parsed_markdown_key:
        raise ValueError("文档解析未完成，缺少 parsed markdown，无法发布索引")


async def review_document(
    db: AsyncSession,
    doc: Document,
    reviewer_id: int,
    action: str,
    reason: str | None = None,
) -> Document:
    if doc.status != DocumentStatus.PENDING_REVIEW.value:
        raise ValueError("只有待审核文档可以审核")

    if action == "approve":
        _ensure_parse_ready_for_approve(doc)
        doc.status = DocumentStatus.PUBLISHED.value
        doc.reviewed_by_id = reviewer_id
        doc.reviewed_at = datetime.now(timezone.utc)
        doc.reject_reason = None
        doc.vector_done = False
        doc.graph_done = False
        await db.flush()

        # 投递 RabbitMQ
        await publish_document_published(doc.id)

        doc.status = DocumentStatus.PROCESSING.value
        await write_audit_log(db, reviewer_id, "approve", "document", doc.id, doc.title)

    elif action == "reject":
        doc.status = DocumentStatus.REJECTED.value
        doc.reviewed_by_id = reviewer_id
        doc.reviewed_at = datetime.now(timezone.utc)
        doc.reject_reason = reason
        await write_audit_log(db, reviewer_id, "reject", "document", doc.id, reason)

    else:
        raise ValueError("action 只能是 approve 或 reject")

    await db.flush()
    await db.refresh(doc)
    return doc