from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.infra.db import get_db
from app.models.user import User
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.permission_service import get_accessible_owner_ids
from app.services.search_service import do_search

router = APIRouter()


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),  # 新增
):
    owner_ids = await get_accessible_owner_ids(db, current_user)
    result = do_search(q, owner_ids, page, page_size)
    # 写搜索日志（6C 建好表后启用）
    from app.models.audit_log import SearchLog

    db.add(SearchLog(user_id=current_user.id, query=q, result_count=result.total))
    await db.flush()
    return result
