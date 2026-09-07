from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    file_name: str
    file_size: int
    file_type: str
    status: str
    owner_id: int
    visibility: str = "private"  # 新增
    department_id: int | None = None  # 新增
    created_at: datetime
    reviewed_by_id: int | None = None
    reviewed_at: datetime | None = None
    reject_reason: str | None = None
    vector_done: bool = False
    graph_done: bool = False
    parse_status: str = "pending"
    parse_error: str | None = None
    parsed_markdown_key: str | None = None
    parse_metadata: dict | None = None
    media_category: str = "document"


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentResponse]


class DocumentUploadResponse(BaseModel):
    message: str = "上传成功"
    document: DocumentResponse


class DocumentUpdateRequest(BaseModel):
    """PATCH 修改可见性"""

    visibility: Literal["private", "department", "public"] | None = None
    department_id: int | None = None

class DocumentReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = Field(None, max_length=500, description="拒绝原因")


class DocumentReviewResponse(BaseModel):
    message: str
    document: DocumentResponse

    
class ParsedPreviewResponse(BaseModel):
    """解析预览：pending / parsing / parsed / failed"""

    status: str
    markdown: str | None = None
    error: str | None = None
    metadata: dict | None = None
    document_id: int | None = None
    file_name: str | None = None
    media_category: str | None = None