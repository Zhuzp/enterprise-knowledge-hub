from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    department = relationship("Department", back_populates="users")
    roles = relationship("UserRole", back_populates="user")
    documents = relationship("Document", foreign_keys="Document.owner_id", back_populates="owner")
    reviewed_documents = relationship(
        "Document", foreign_keys="Document.reviewed_by_id", back_populates="reviewer"
    )
