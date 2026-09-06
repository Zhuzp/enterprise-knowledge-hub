from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import settings


class Base(DeclarativeBase):
    pass


#- 创建异步数据库引擎 `engine`
engine = create_async_engine(
    settings.database_url,
    echo=True,  # 开发时打印 SQL，上线可改 False
    pool_pre_ping=True,
)

#创建异步会话工厂 `AsyncSessionLocal`
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# FastAPI依赖：提供数据库会话
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # 没异常就提交
        except Exception:
            await session.rollback()  # 有异常就回滚
            raise
        finally:
            await session.close()
