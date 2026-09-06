from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def write_audit_log(
    db: AsyncSession,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    detail: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
        )
    )
    await db.flush()
