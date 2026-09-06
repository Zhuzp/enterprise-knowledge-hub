很好，阶段 3 你已经写完了。下面按**从整体到细节**的方式，把文档管理这套代码逐段讲清楚。

---

## 一、整体设计：文件存两份

文档管理用了**双存储**：

```
上传一个 PDF
  ├── MinIO（对象存储）→ 存原始文件字节
  └── PostgreSQL（数据库）→ 存元数据（标题、大小、路径、归属）
```

为什么不只存数据库？  
文件可能几十 MB，PostgreSQL 不适合存大文件；MinIO 类似 AWS S3，专门存文件，更便宜、更快。

```
┌─────────────┐     元数据      ┌──────────────┐
│  PostgreSQL  │ ←──────────→ │  FastAPI API  │
│  documents表 │               └──────┬───────┘
└─────────────┘                      │ 文件读写
                                     ↓
                              ┌──────────────┐
                              │    MinIO     │
                              │  原始文件存储  │
                              └──────────────┘
```

---

## 二、各文件分工

| 文件 | 层级 | 职责 |
|------|------|------|
| `settings.py` | 配置 | MinIO 地址、上传限制 |
| `models/document.py` | 数据层 | 定义 `documents` 表 |
| `schemas/document.py` | 接口层 | 定义 API 入参/出参格式 |
| `infra/minio_client.py` | 基础设施 | 封装 MinIO 上传/下载/删除 |
| `api/v1/documents.py` | 业务层 | 5 个 HTTP 接口 |
| `main.py` | 入口 | 挂载路由 |

---

## 三、逐文件讲解

### 1. `settings.py` — 新增的配置项

```19:38:d:\code\python\enterprise-knowledge-hub\app\core\settings.py
    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "documents"
    minio_secure: bool = False

    # 上传限制
    max_upload_size_mb: int = 50
    allowed_file_types: str = "pdf,docx,md,txt"  # 逗号分隔

    @property
    def database_url(self) -> str:
        ...

    @property
    def allowed_extensions(self) -> set[str]:
        return {f".{ext.strip()}" for ext in self.allowed_file_types.split(",")}
```

| 配置 | 作用 |
|------|------|
| `minio_endpoint` | MinIO 服务地址，如 `127.0.0.1:9000` |
| `minio_access_key / secret_key` | 访问 MinIO 的账号密码 |
| `minio_bucket` | 存储桶名，类似文件夹 |
| `minio_secure` | 是否 HTTPS，`False` 表示本地 HTTP |
| `max_upload_size_mb` | 单文件最大 50MB |
| `allowed_file_types` | 允许的类型 |
| `allowed_extensions` | 把 `"pdf,docx"` 转成 `{".pdf", ".docx"}`，方便校验 |

**为什么用 `@property`？**  
`.env` 里写的是 `"pdf,docx,md,txt"` 字符串，代码里需要 `set` 集合做 `in` 判断，所以在读取时自动转换。

---

### 2. `models/document.py` — 文档表结构

#### 状态枚举

```10:13:d:\code\python\enterprise-knowledge-hub\app\models\document.py
class DocumentStatus(str, Enum):
    PENDING = "pending"  # 刚上传，待处理
    READY = "ready"  # 可用
    FAILED = "failed"  # 处理失败
```

| 状态 | 含义 | 什么时候用 |
|------|------|-----------|
| `pending` | 刚上传，还没处理 | 默认值，阶段 4 解析前 |
| `ready` | 正常可用 | 上传成功 / 解析完成 |
| `failed` | 处理失败 | 阶段 4 解析出错时 |

阶段 4 做文档解析时会用到：上传后 `pending` → 解析成功 `ready` → 解析失败 `failed`。

#### 表字段

```16:33:d:\code\python\enterprise-knowledge-hub\app\models\document.py
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    file_type: Mapped[str] = mapped_column(String(20))  # pdf / docx / md / txt
    minio_key: Mapped[str] = mapped_column(String(500))  # MinIO 里的路径
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(...)

    owner = relationship("User", backref="documents")
```

| 字段 | 作用 | 示例 |
|------|------|------|
| `title` | 显示标题 | "员工手册" |
| `file_name` | 原始文件名 | "handbook.pdf" |
| `file_size` | 大小（字节） | 2048576（约 2MB） |
| `file_type` | 类型 | "pdf" |
| `minio_key` | MinIO 里的路径 | `users/1/a3b2c1d4_handbook.pdf` |
| `owner_id` | 外键，关联上传者 | `1` → users 表的 id |
| `status` | 文档状态 | "ready" |
| `owner = relationship(...)` | ORM 关联 | 可通过 `doc.owner` 拿到 User 对象 |

**`minio_key` 是关键字段：**  
数据库不存文件内容，只存 MinIO 路径；下载时用 `minio_key` 去 MinIO 取文件。

**`ForeignKey("users.id")`：**  
保证 `owner_id` 必须是真实存在的用户，不能乱写。

---

### 3. `schemas/document.py` — API 数据格式

```6:26:d:\code\python\enterprise-knowledge-hub\app\schemas\document.py
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    file_name: str
    file_size: int
    file_type: str
    status: str
    owner_id: int
    created_at: datetime


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentResponse]


class DocumentUploadResponse(BaseModel):
    message: str = "上传成功"
    document: DocumentResponse
```

| 类 | 用于哪个接口 | 返回示例 |
|----|-------------|---------|
| `DocumentResponse` | 详情、上传 | 单个文档信息 |
| `DocumentListResponse` | 列表 | `{"total": 5, "items": [...]}` |
| `DocumentUploadResponse` | 上传 | `{"message": "上传成功", "document": {...}}` |

**注意：** 响应里**没有 `minio_key`**。  
MinIO 路径是内部实现细节，不暴露给前端，更安全。

---

### 4. `infra/minio_client.py` — MinIO 操作封装

#### 创建客户端

```9:14:d:\code\python\enterprise-knowledge-hub\app\infra\minio_client.py
minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)
```

全局单例，整个应用共用一个 MinIO 连接。

#### 四个核心函数

**① `ensure_bucket_exists()` — 确保存储桶存在**

```17:21:d:\code\python\enterprise-knowledge-hub\app\infra\minio_client.py
def ensure_bucket_exists() -> None:
    bucket = settings.minio_bucket
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)
```

Bucket 类似顶层文件夹；不存在就自动创建，避免第一次上传失败。

**② `generate_object_key()` — 生成唯一存储路径**

```24:27:d:\code\python\enterprise-knowledge-hub\app\infra\minio_client.py
def generate_object_key(owner_id: int, file_name: str) -> str:
    unique_id = uuid4().hex[:8]
    return f"users/{owner_id}/{unique_id}_{file_name}"
```

生成路径如：`users/1/a3b2c1d4_员工手册.pdf`

| 部分 | 作用 |
|------|------|
| `users/1/` | 按用户分目录 |
| `a3b2c1d4_` | UUID 防重名 |
| `员工手册.pdf` | 保留原文件名 |

**③ `upload_file()` — 上传**

```30:39:d:\code\python\enterprise-knowledge-hub\app\infra\minio_client.py
def upload_file(file_data: bytes, object_key: str, content_type: str) -> None:
    ensure_bucket_exists()
    minio_client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=object_key,
        data=BytesIO(file_data),
        length=len(file_data),
        content_type=content_type,
    )
```

| 参数 | 含义 |
|------|------|
| `file_data` | 文件二进制内容 |
| `object_key` | 存到哪 |
| `content_type` | MIME 类型，如 `application/pdf` |
| `BytesIO(file_data)` | 把 bytes 包装成类文件对象 |

**④ `download_file()` / `delete_file()`**

```42:54:d:\code\python\enterprise-knowledge-hub\app\infra\minio_client.py
def download_file(object_key: str) -> bytes:
    response = minio_client.get_object(settings.minio_bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()

def delete_file(object_key: str) -> None:
    minio_client.remove_object(settings.minio_bucket, object_key)
```

`finally` 确保连接释放，避免泄漏。

---

### 5. `api/v1/documents.py` — 核心业务（重点）

#### 辅助：MIME 类型映射

```19:25:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
CONTENT_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}
```

浏览器靠 MIME 类型决定怎么处理文件（预览 / 下载）。

#### 辅助：`validate_file()` — 文件校验

```28:41:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
def validate_file(file: UploadFile) -> tuple[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    _, ext = os.path.splitext(file.filename.lower())
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，允许: {settings.allowed_file_types}",
        )

    file_type = ext.lstrip(".")  # ".pdf" → "pdf"
    return ext, file_type
```

| 步骤 | 做什么 |
|------|--------|
| 检查文件名 | 空文件名 → 400 |
| 取扩展名 | `"Handbook.PDF"` → `".pdf"` |
| 白名单校验 | `.exe` → 400 |
| 返回 | `(".pdf", "pdf")` |

---

#### 接口 1：上传 `POST /api/v1/documents`

```44:84:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```

**完整流程：**

```
1. Depends(get_current_user)  → 必须登录，拿到当前用户
2. validate_file(file)         → 校验文件类型
3. file_data = await file.read() → 读取文件到内存
4. 检查 file_size 是否超限
5. generate_object_key()       → 生成 MinIO 路径
6. upload_file()               → 文件存到 MinIO
7. Document(...) + db.add()    → 元数据存到 PostgreSQL
8. return DocumentUploadResponse
```

逐步说明：

| 代码 | 作用 |
|------|------|
| `file: UploadFile = File(...)` | FastAPI 接收 multipart 文件；`...` 表示必填 |
| `title: str \| None = None` | 可选标题，不传则用文件名 |
| `await file.read()` | 异步读取全部内容到 bytes |
| `max_bytes = 50 * 1024 * 1024` | 50MB 限制 |
| `title or file.filename` | 没传 title 就用文件名 |
| `status=DocumentStatus.READY.value` | 阶段 3 直接 ready；阶段 4 可改为 pending |

**为什么先传 MinIO 再写数据库？**  
MinIO 失败就不写库，避免「库里有记录但文件不存在」。

---

#### 接口 2：列表 `GET /api/v1/documents`

```87:111:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    ...
):
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.owner_id == current_user.id)
    )
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == current_user.id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = result.scalars().all()

    return DocumentListResponse(total=total, items=items)
```

| 概念 | 代码 | 作用 |
|------|------|------|
| 分页 | `page=1, page_size=20` | 第 1 页，每页 20 条 |
| 偏移 | `offset = (page-1) * page_size` | 第 2 页 → 跳过 20 条 |
| 总数 | `func.count()` | 前端算总页数 |
| 排序 | `.order_by(created_at.desc())` | 最新在前 |
| 隔离 | `owner_id == current_user.id` | 只看自己的文档 |

等价 SQL：

```sql
SELECT COUNT(*) FROM documents WHERE owner_id = 1;
SELECT * FROM documents WHERE owner_id = 1 ORDER BY created_at DESC LIMIT 20 OFFSET 0;
```

---

#### 接口 3：详情 `GET /api/v1/documents/{doc_id}`

```114:124:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
async def get_document(doc_id: int, ...):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.owner_id == current_user.id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc
```

两个条件：`id` 匹配 **且** `owner_id` 是当前用户。  
别人文档即使猜到 id 也拿不到 → **404**，不是 403，避免泄露「文档是否存在」。

---

#### 接口 4：下载 `GET /api/v1/documents/{doc_id}/download`

```127:145:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
async def download_document(doc_id: int, ...):
    ...
    file_data = download_file(doc.minio_key)
    content_type = CONTENT_TYPE_MAP.get(f".{doc.file_type}", "application/octet-stream")

    return StreamingResponse(
        BytesIO(file_data),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.file_name}"'},
    )
```

流程：

```
查 documents 表 → 拿到 minio_key → MinIO 下载 bytes → 流式返回给浏览器
```

| 概念 | 作用 |
|------|------|
| `StreamingResponse` | 流式响应，适合大文件 |
| `Content-Disposition: attachment` | 告诉浏览器「下载」而不是「打开」 |
| `filename="..."` | 下载时的文件名 |

---

#### 接口 5：删除 `DELETE /api/v1/documents/{doc_id}`

```148:162:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
async def delete_document(doc_id: int, ...):
    ...
    delete_file(doc.minio_key)   # 先删 MinIO 文件
    await db.delete(doc)          # 再删数据库记录
```

**先删文件再删记录。**  
返回 `204 No Content`，表示成功且无响应体。

---

### 6. `main.py` — 挂载文档路由

```1:9:d:\code\python\enterprise-knowledge-hub\app\main.py
from app.api.v1.documents import router as documents_router

app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])
```

最终路由：

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/documents` | 上传 |
| GET | `/api/v1/documents` | 列表 |
| GET | `/api/v1/documents/{id}` | 详情 |
| GET | `/api/v1/documents/{id}/download` | 下载 |
| DELETE | `/api/v1/documents/{id}` | 删除 |

---

## 四、一次上传的完整链路

```
前端: POST /api/v1/documents
      Header: Authorization: Bearer eyJ...
      Body: file=handbook.pdf, title=员工手册

  ↓
① get_current_user → 解析 Token → user.id = 1

  ↓
② validate_file → ".pdf" 在白名单内 ✓

  ↓
③ file.read() → 2048576 bytes，小于 50MB ✓

  ↓
④ generate_object_key(1, "handbook.pdf")
   → "users/1/a3b2c1d4_handbook.pdf"

  ↓
⑤ upload_file → MinIO 存储文件

  ↓
⑥ INSERT INTO documents (title, file_name, minio_key, owner_id, ...)
   → id = 1

  ↓
⑦ 返回 JSON:
   {
     "message": "上传成功",
     "document": {
       "id": 1,
       "title": "员工手册",
       "file_name": "handbook.pdf",
       "file_size": 2048576,
       "file_type": "pdf",
       "status": "ready",
       "owner_id": 1,
       "created_at": "2026-08-24T..."
     }
   }
```

---

## 五、和阶段 2（认证）的关系

```
阶段 2 提供的能力          阶段 3 怎么用
─────────────────────────────────────────
get_current_user    →   每个文档接口都要登录
User.id             →   写入 owner_id，数据隔离
JWT Token           →   前端 Authorization 头
Depends 注入        →   同样模式注入 db、current_user
Model + Schema 分层 →   Document + DocumentResponse
Alembic 迁移        →   同样方式建 documents 表
```

阶段 3 没有新架构模式，是在阶段 2 基础上**加模块**。

---

## 六、和后续阶段的关系

| 阶段 3 留的接口 | 阶段 4 怎么用 |
|----------------|--------------|
| `status = pending` | 上传后待解析 |
| `minio_key` | Worker 按路径下载文件 |
| `file_type` | 决定用 pypdf 还是 python-docx |
| `DocumentStatus.READY` | 解析完改状态 |

阶段 4 会加：

```
上传 (status=pending)
  → Redis 队列
  → Worker: MinIO 下载 → 解析文本 → 分块
  → ElasticSearch 索引
  → status=ready
```

---

## 七、关键概念小结

| 概念 | 在本项目中的体现 |
|------|----------------|
| 双存储 | PostgreSQL 元数据 + MinIO 文件 |
| 外键 | `owner_id → users.id` |
| 分页 | `offset + limit` |
| 权限隔离 | 所有查询带 `owner_id == current_user.id` |
| 文件校验 | 类型白名单 + 大小限制 |
| 流式下载 | `StreamingResponse` |
| 依赖注入 | `Depends(get_current_user)` 保护接口 |

---

如果你想继续深入，我可以单独展开：

1. **`UploadFile` 原理** — FastAPI 怎么接收文件  
2. **MinIO vs 本地磁盘** — 为什么用对象存储  
3. **阶段 4** — 文档解析 + ElasticSearch 搜索怎么接  

你想先听哪个，或者直接开始阶段 4？