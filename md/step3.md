你现在已经把**阶段 4（解析 + 搜索）**接上了。下面从**整体链路 → 每个文件 → 每段代码**说明它们各自在做什么。

你打开的 `documents.py` 里新增了关键一行：

```84:84:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
    await process_document(doc.id, db)
```

上传不再只是「存文件」，而是会**自动解析、分块、建索引**。

---

## 一、阶段 4 解决什么问题？

阶段 3 只能「存文件、下载文件」，**搜不到内容**。

阶段 4 把流程变成：

```
上传 PDF
  → 从 MinIO 取出文件
  → 解析成纯文本
  → 切成多个 chunk
  → 写入 PostgreSQL（document_chunks）
  → 索引到 ElasticSearch
  → GET /api/v1/search?q=年假 能搜到内容
```

---

## 二、整体数据流

```
┌──────────┐    上传     ┌─────────┐    存文件    ┌───────┐
│  前端     │ ─────────→ │documents│ ──────────→ │ MinIO │
└──────────┘             │  .py    │              └───────┘
                         │         │    元数据     ┌──────────┐
                         │         │ ──────────→ │ documents │
                         │         │              └──────────┘
                         │process_ │
                         │document  │
                         └────┬────┘
                              │
         ┌────────────────────┼────────────────────┐
         ↓                    ↓                    ↓
    parser.py           chunker.py           es_client.py
    解析文本             切分 chunk            建 ES 索引
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ↓
                    ┌─────────────────┐
                    │ document_chunks │（PostgreSQL）
                    └─────────────────┘
                              ↓
                    ┌─────────────────┐
                    │ ElasticSearch   │（全文检索）
                    └─────────────────┘
                              ↓
                    search.py → 返回搜索结果
```

**三份存储各司其职：**

| 存储 | 存什么 | 作用 |
|------|--------|------|
| MinIO | 原始文件（PDF 字节） | 下载、重新解析 |
| PostgreSQL `document_chunks` | 文本块 | 持久化、给 AI 问答用 |
| ElasticSearch | 可搜索索引 | 关键词全文检索 |

---

## 三、逐文件讲解

### 1. `models/document_chunk.py` — 文本块表

```9:22:d:\code\python\enterprise-knowledge-hub\app\models\document_chunk.py
class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)  # 第几块，从 0 开始
    content: Mapped[str] = mapped_column(Text)  # 文本内容
    es_doc_id: Mapped[str | None] = mapped_column(String(100))  # ES 里的文档 ID
    ...
    document = relationship("Document", backref="chunks")
```

| 字段 | 作用 | 示例 |
|------|------|------|
| `document_id` | 属于哪篇文档 | `1` → 员工手册 |
| `chunk_index` | 第几块 | `0, 1, 2...` |
| `content` | 这块的文本 | 「年假规定：员工每年享有 10 天年假...」 |
| `es_doc_id` | ES 里对应记录 ID | `doc_1_chunk_3` |

**为什么要分块？**  
一篇文档可能几千字，整篇塞进 ES 不利于精准匹配；切成小块后，搜索能定位到**具体段落**。

---

### 2. `services/parser.py` — 文档解析

```7:41:d:\code\python\enterprise-knowledge-hub\app\services\parser.py
def parse_pdf(file_data: bytes) -> str:
    reader = PdfReader(BytesIO(file_data))
    ...
def parse_docx(file_data: bytes) -> str:
    doc = DocxDocument(BytesIO(file_data))
    ...
def parse_text(file_data: bytes) -> str:
    return file_data.decode("utf-8")

def parse_document(file_data: bytes, file_type: str) -> str:
    parsers = {
        "pdf": parse_pdf,
        "docx": parse_docx,
        "md": parse_text,
        "txt": parse_text,
    }
    ...
```

| 函数 | 输入 | 输出 |
|------|------|------|
| `parse_pdf` | PDF 字节 | 全部页面拼成的纯文本 |
| `parse_docx` | Word 字节 | 所有段落拼成的文本 |
| `parse_text` | md/txt 字节 | UTF-8 解码 |
| `parse_document` | 字节 + 类型 | 自动选解析器 |

**`BytesIO(file_data)` 的作用：**  
解析库需要「类文件对象」，把 `bytes` 包一层，不用落盘。

**策略模式：** `parsers` 字典按 `file_type` 选函数，加新格式只需多写一个 parser。

---

### 3. `services/chunker.py` — 文本分块

```4:27:d:\code\python\enterprise-knowledge-hub\app\services\chunker.py
def split_text(text: str) -> list[str]:
    chunk_size = settings.chunk_size      # 500
    overlap = settings.chunk_overlap      # 50
    ...
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # 尽量在句号/换行处切断
        if end < len(text):
            for sep in ["\n\n", "\n", "。", "."]:
                last_sep = chunk.rfind(sep)
                if last_sep > chunk_size // 2:
                    chunk = chunk[: last_sep + len(sep)]
                    end = start + len(chunk)
                    break

        chunks.append(chunk.strip())
        start = end - overlap  # 重叠 50 字符
```

**举例：** 一篇 1200 字的文档

```
Chunk 0: 字符 0~500   「第一章 总则...年假规定...」
Chunk 1: 字符 450~950  （从 450 开始，重叠 50 字）
Chunk 2: 字符 900~1200
```

| 设计 | 作用 |
|------|------|
| 在 `\n\n`、句号处切 | 避免「年假10」和「天带薪」被拆开 |
| `overlap = 50` | 块边界附近的内容两边 chunk 都有，搜索更稳 |
| 过滤空块 | 去掉纯空白 chunk |

---

### 4. `infra/es_client.py` — ElasticSearch 操作

#### 创建索引

```8:25:d:\code\python\enterprise-knowledge-hub\app\infra\es_client.py
def ensure_index_exists() -> None:
    if not es_client.indices.exists(index=settings.es_index):
        es_client.indices.create(
            index=settings.es_index,
            body={
                "mappings": {
                    "properties": {
                        "document_id": {"type": "integer"},
                        "chunk_id": {"type": "integer"},
                        "owner_id": {"type": "integer"},
                        "title": {"type": "text"},
                        "content": {"type": "text", "analyzer": "standard"},
                        "file_type": {"type": "keyword"},
                    }
                }
            },
        )
```

| 字段类型 | 含义 |
|----------|------|
| `text` + `analyzer: standard` | 会被分词，用于全文搜索 |
| `keyword` | 不分词，精确匹配 |
| `integer` | 数字，用于 filter |

`content` 用 `text` → 搜「年假」能匹配「年假规定」。  
`owner_id` 用 filter → 只搜自己的文档。

#### 索引一个 chunk

```28:51:d:\code\python\enterprise-knowledge-hub\app\infra\es_client.py
def index_chunk(...) -> str:
    es_doc_id = f"doc_{document_id}_chunk_{chunk_id}"
    es_client.index(
        index=settings.es_index,
        id=es_doc_id,
        body={...},
    )
    return es_doc_id
```

每个 chunk 在 ES 里是一条独立文档，ID 如 `doc_1_chunk_3`。

#### 搜索

```54:86:d:\code\python\enterprise-knowledge-hub\app\infra\es_client.py
    result = es_client.search(
        index=settings.es_index,
        body={
            "query": {
                "bool": {
                    "must": [
                        {"match": {"content": query}},
                    ],
                    "filter": [
                        {"term": {"owner_id": owner_id}},
                    ],
                }
            },
            "highlight": {
                "fields": {"content": {}},
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
            },
        },
    )
```

| 部分 | 作用 |
|------|------|
| `bool.must` + `match` | 内容里要匹配关键词 |
| `bool.filter` + `term` | 必须是当前用户的文档 |
| `highlight` | 命中词用 `<em>` 包起来 |

搜「年假」可能返回：

```html
员工每年享有 <em>年假</em> 10 天...
```

#### 删除索引

```89:97:d:\code\python\enterprise-knowledge-hub\app\infra\es_client.py
def delete_document_chunks(document_id: int) -> None:
    es_client.delete_by_query(
        body={"query": {"term": {"document_id": document_id}}},
    )
```

删文档时，按 `document_id` 批量删 ES 里所有 chunk 索引。

---

### 5. `services/index_service.py` — 解析流水线（核心）

```12:53:d:\code\python\enterprise-knowledge-hub\app\services\index_service.py
async def process_document(document_id: int, db: AsyncSession) -> int:
    # 1. 查文档
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    ...
    # 2. 从 MinIO 下载
    file_data = download_file(doc.minio_key)
    # 3. 解析文本
    text = parse_document(file_data, doc.file_type)
    if not text.strip():
        doc.status = DocumentStatus.FAILED.value
        return 0
    # 4. 分块
    chunks = split_text(text)
    # 5. 写入 document_chunks + 索引 ES
    for i, chunk_text in enumerate(chunks):
        chunk = DocumentChunk(...)
        db.add(chunk)
        await db.flush()
        es_doc_id = index_chunk(...)
        chunk.es_doc_id = es_doc_id
    doc.status = DocumentStatus.READY.value
    return len(chunks)
```

**五步流水线：**

```
查 documents 表 → MinIO 下载 → parser 解析 → chunker 分块 → PG + ES 双写
```

| 步骤 | 失败时 |
|------|--------|
| 解析出空文本 | `status = failed`，返回 0 |
| 正常完成 | `status = ready`，返回 chunk 数量 |

**为什么先 `flush` 再 `index_chunk`？**  
`flush` 后 chunk 才有数据库自增 `id`，才能生成 `doc_1_chunk_3` 这类 ES ID。

`reindex_document`：先删旧 chunks 和 ES 索引，再重新 `process_document`，用于「重新解析」场景。

---

### 6. `documents.py` 里的衔接（你打开的文件）

上传接口里新增的关键代码：

```71:86:d:\code\python\enterprise-knowledge-hub\app\api\v1\documents.py
    doc = Document(...)
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    await process_document(doc.id, db)   # ← 新增：上传后自动解析索引

    return DocumentUploadResponse(document=doc)
```

**一次上传的完整链路：**

```
① validate_file          校验类型
② upload_file            存 MinIO
③ db.add(doc)            写 documents 表
④ process_document       解析 → 分块 → 索引
⑤ return                 返回文档信息
```

用户上传后**同步**完成索引（阶段 5 可改成 Redis 异步 Worker，上传更快返回）。

---

### 7. `schemas/search.py` + `search_service.py` — 搜索结果

```4:16:d:\code\python\enterprise-knowledge-hub\app\schemas\search.py
class SearchResultItem(BaseModel):
    document_id: int
    chunk_id: int
    title: str
    content: str
    highlight: str | None = None
    score: float
```

| 字段 | 含义 |
|------|------|
| `content` | chunk 原文（截断前 200 字） |
| `highlight` | 带高亮的片段 |
| `score` | ES 相关度分数，越高越相关 |

```5:29:d:\code\python\enterprise-knowledge-hub\app\services\search_service.py
def do_search(query, owner_id, page, page_size):
    result = search_documents(...)
    hits = result["hits"]["hits"]
    total = result["hits"]["total"]["value"]
    ...
    content=source["content"][:200]  # 截取前 200 字
    highlight=hit["highlight"]["content"][0]
    score=hit["_score"]
```

把 ES 的复杂 JSON 转成前端友好的结构。

---

### 8. `api/v1/search.py` — 搜索接口

```11:19:d:\code\python\enterprise-knowledge-hub\app\api\v1\search.py
@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    results = do_search(q, current_user.id, page, page_size)
    return results
```

| 参数 | 约束 | 作用 |
|------|------|------|
| `q` | 至少 1 字符 | 搜索词 |
| `page` | ≥ 1 | 页码 |
| `page_size` | 1~50 | 每页条数 |

调用：`GET /api/v1/search?q=年假&page=1&page_size=10`

---

## 四、一次搜索的完整链路

```
GET /api/v1/search?q=年假
  ↓
get_current_user → owner_id = 1
  ↓
do_search("年假", 1, 1, 10)
  ↓
ES 查询:
  match content="年假" AND owner_id=1
  ↓
ES 返回 3 条命中
  ↓
组装 SearchResponse:
{
  "query": "年假",
  "total": 3,
  "items": [
    {
      "document_id": 1,
      "chunk_id": 2,
      "title": "员工手册",
      "content": "员工每年享有年假 10 天...",
      "highlight": "员工每年享有 <em>年假</em> 10 天...",
      "score": 1.85
    }
  ]
}
```

---

## 五、各层职责对照

| 文件 | 层级 | 一句话 |
|------|------|--------|
| `document_chunk.py` | 数据 | 定义 chunk 表 |
| `parser.py` | 服务 | 文件 → 纯文本 |
| `chunker.py` | 服务 | 长文本 → 多个 chunk |
| `es_client.py` | 基础设施 | ES 增删查 |
| `index_service.py` | 服务 | 串联解析流水线 |
| `search_service.py` | 服务 | ES 结果 → API 格式 |
| `search.py` | 接口 | 暴露搜索 API |
| `documents.py` | 接口 | 上传后触发 `process_document` |

---

## 六、和后续阶段 5 的关系

阶段 4 是 **关键词匹配**（搜「年假」要有「年假」这个词）。

阶段 5 AI 问答会复用同一套数据：

```
用户问「带薪休假有几天？」（没出现「年假」）
  ↓
阶段 4：可能搜不到（关键词不匹配）
  ↓
阶段 5：向量检索 + LLM
  → 用 document_chunks 的内容
  → LLM 生成「根据员工手册，年假为 10 天」
  → 附带引用来源
```

`document_chunks` 表就是为 RAG 准备的；ES 索引也可扩展向量字段做混合检索。

---

## 七、关键概念小结

| 概念 | 在本项目中的体现 |
|------|------------------|
| 文档解析 | `parser.py` 多格式转文本 |
| Chunking | `chunker.py` 固定长度 + overlap |
| 全文索引 | ES `text` + `match` 查询 |
| 权限过滤 | ES `filter: owner_id` |
| 高亮 | ES `highlight` |
| 双写 | chunk 同时写 PG 和 ES |
| 流水线 | `index_service.process_document` |

---

如果你想继续深入，可以选一个方向：

1. **ES 查询 DSL** — `bool`、`match`、`term` 区别  
2. **Chunking 策略** — 为什么 500 字、overlap 多少合适  
3. **阶段 5** — 在现有 chunks 上接 LangGraph RAG 问答  

你想先听哪个，或者直接开始阶段 5？