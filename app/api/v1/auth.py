from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.infra.db import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserResponse

router = APIRouter()


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    # 1. 检查用户名或邮箱是否已存在
    result = await db.execute(
        select(User).where(
            or_(User.username == data.username, User.email == data.email)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名或邮箱已存在",
        )

    # 2. 创建用户
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()  # 拿到自增 id，但还没 commit
    await db.refresh(user)  # 刷新 created_at 等字段

    return user


@router.post("/login", response_model=Token)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    # 1. 查用户
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    # 2. 验证密码（统一错误信息，防止枚举用户名）
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 3. 生成 Token 
    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
