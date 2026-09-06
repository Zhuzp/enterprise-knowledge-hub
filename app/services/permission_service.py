from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentVisibility
from app.models.role import Role, UserRole
from app.models.user import User


async def get_user_role_names(db: AsyncSession, user_id: int) -> set[str]:
    result = await db.execute(
        select(Role.name).join(UserRole).where(UserRole.user_id == user_id)
    )
    return {row[0] for row in result.all()}


async def is_admin(db: AsyncSession, user_id: int) -> bool:
    return "admin" in await get_user_role_names(db, user_id)


async def get_document_filter(user: User, admin: bool):
    if admin:
        return True
    visibility_conditions = or_(
        Document.owner_id == user.id,
        Document.visibility == DocumentVisibility.PUBLIC.value,
        *(
            [
                (Document.visibility == DocumentVisibility.DEPARTMENT.value)
                & (Document.department_id == user.department_id)
            ]
            if user.department_id
            else []
        ),
    )
    # 非 owner 只能看到已发布文档；owner 可看到自己所有状态的文档
    status_conditions = or_(
        Document.status == DocumentStatus.READY.value,
        Document.owner_id == user.id,
    )
    return visibility_conditions & status_conditions


async def get_accessible_owner_ids(db: AsyncSession, user: User) -> list[int] | None:
    """搜索/RAG 用：只返回 ready 文档的 owner_id"""
    if await is_admin(db, user.id):
        return None
    owner_ids = {user.id}
    if user.department_id:
        result = await db.execute(
            select(Document.owner_id).where(
                Document.department_id == user.department_id,
                Document.visibility.in_(["department", "public"]),
                Document.status == DocumentStatus.READY.value,
            )
        )
        owner_ids.update(r[0] for r in result.all())
    result = await db.execute(
        select(Document.owner_id).where(
            Document.visibility == "public",
            Document.status == DocumentStatus.READY.value,
        )
    )
    owner_ids.update(r[0] for r in result.all())
    return list(owner_ids)