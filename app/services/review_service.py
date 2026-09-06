from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.rabbitmq_client import publish_document_published
from app.models.document import Document, DocumentStatus
from app.services.audit_service import write_audit_log


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