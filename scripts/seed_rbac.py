"""初始化部门、角色、管理员。用法: python -m scripts.seed_rbac"""

import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.infra.db import AsyncSessionLocal
from app.models.department import Department
from app.models.role import Role, UserRole
from app.models.user import User


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # 部门
        for name in ["研发部", "产品部", "人事部"]:
            exists = (await db.execute(select(Department).where(Department.name == name))).scalar_one_or_none()
            if not exists:
                db.add(Department(name=name))

        # 角色
        for name in ["admin", "user"]:
            exists = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
            if not exists:
                db.add(Role(name=name))
        await db.flush()

        admin_role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one()
        dev_dept = (await db.execute(select(Department).where(Department.name == "研发部"))).scalar_one()

        # 管理员（不存在则创建）
        admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
        if admin is None:
            admin = User(
                username="admin",
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                department_id=dev_dept.id,
            )
            db.add(admin)
            await db.flush()

        # 绑定 admin 角色
        link = (
            await db.execute(select(UserRole).where(UserRole.user_id == admin.id, UserRole.role_id == admin_role.id))
        ).scalar_one_or_none()
        if link is None:
            db.add(UserRole(user_id=admin.id, role_id=admin_role.id))

        await db.commit()
        print("Seed 完成: admin / admin123")


if __name__ == "__main__":
    asyncio.run(main())
