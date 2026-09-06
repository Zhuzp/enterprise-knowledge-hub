from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin
from app.infra.db import get_db
from app.models.user import User
from app.services.stats_service import get_hotwords, get_overview

router = APIRouter()


@router.get("/overview")
async def stats_overview(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_overview(db)


@router.get("/search-hotwords")
async def stats_hotwords(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_hotwords(db)
