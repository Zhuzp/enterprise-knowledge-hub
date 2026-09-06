from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import SearchLog
from app.models.chat import QAMessage
from app.models.document import Document, DocumentStatus
from app.models.user import User


async def get_overview(db: AsyncSession) -> dict:
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    doc_count = (await db.execute(select(func.count()).select_from(Document))).scalar() or 0
    ready_doc_count = (
        await db.execute(
            select(func.count()).select_from(Document).where(Document.status == DocumentStatus.READY.value)
        )
    ).scalar() or 0
    pending_review_count = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.status == DocumentStatus.PENDING_REVIEW.value)
        )
    ).scalar() or 0
    qa_count = (
        await db.execute(select(func.count()).select_from(QAMessage).where(QAMessage.role == "user"))
    ).scalar() or 0
    search_count = (await db.execute(select(func.count()).select_from(SearchLog))).scalar() or 0
    return {
        "users": user_count,
        "documents": doc_count,
        "ready_documents": ready_doc_count,
        "pending_review_documents": pending_review_count,
        "qa_messages": qa_count,
        "searches": search_count,
    }


async def get_hotwords(db: AsyncSession, limit: int = 10) -> list[dict]:
    result = await db.execute(
        select(SearchLog.query, func.count().label("cnt"))
        .group_by(SearchLog.query)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [{"query": row[0], "count": row[1]} for row in result.all()]
