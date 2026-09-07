from datetime import datetime
from enum import Enum
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db import Base 

class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"
class MediaCategory(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"

class DocumentStatus(str, Enum):
    PENDING_REVIEW = "pending_review"  # 已上传，待审核
    REJECTED = "rejected"              # 审核拒绝
    PUBLISHED = "published"            # 审核通过，已投递 MQ
    PROCESSING = "processing"          # consumer 处理中
    READY = "ready"                    # 向量+图谱都完成
    FAILED = "failed"                  # 处理失败


class DocumentVisibility(str, Enum):
    PRIVATE = "private"
    DEPARTMENT = "department"
    PUBLIC = "public"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    file_type: Mapped[str] = mapped_column(String(20))  # pdf / docx / md / txt
    minio_key: Mapped[str] = mapped_column(String(500))  # MinIO 里的路径
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING_REVIEW.value)
    # 解析相关（新增）
    parse_status: Mapped[str] = mapped_column(String(20), default=ParseStatus.PENDING.value)
    parse_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parsed_markdown_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parse_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    media_category: Mapped[str] = mapped_column(String(20), default=MediaCategory.DOCUMENT.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reject_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vector_done: Mapped[bool] = mapped_column(default=False)
    graph_done: Mapped[bool] = mapped_column(default=False)

    owner = relationship("User", foreign_keys=[owner_id], back_populates="documents")
    reviewer = relationship("User", foreign_keys=[reviewed_by_id], back_populates="reviewed_documents")
    visibility: Mapped[str] = mapped_column(
        String(20), default=DocumentVisibility.PRIVATE.value
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
