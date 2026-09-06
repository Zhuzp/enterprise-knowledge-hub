## 整体思路

| 环境 | 推荐 |
|------|------|
| 本地开发 | 继续用 **LangSmith**（已配好） |
| 线上 / 自建 | 加 **Langfuse**（数据在自己服务器） |

Langfuse 和 LangSmith **可以同时开**（两个 callback 一起传），但一般 **开发关 Langfuse、线上关 LangSmith**，避免重复上报。

---

## 1. 依赖

```txt
# requirements.txt 追加
langfuse>=3.0.0
```

```powershell
pip install langfuse
```

---

## 2. `.env` 配置

**本地验证**（二选一）：

```env
# 方案 A：Langfuse 云服务（最简单，不用 Docker）
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com

# 方案 B：本地 Docker 自建
# LANGFUSE_BASE_URL=http://localhost:3000

# 线上建议关掉 LangSmith，避免双写
LANGCHAIN_TRACING_V2=false
```

Keys 在 Langfuse 项目 → **Settings → API Keys** 创建。

---

## 3. `settings.py` 追加

```python
# Langfuse（生产/本地自建）
langfuse_enabled: bool = False
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_base_url: str = "http://localhost:3000"
```

```python
def _init_langfuse() -> None:
    """初始化 Langfuse 客户端，SDK 从 os.environ 读配置"""
    import os

    if not settings.langfuse_enabled:
        return
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url
    # 可选：调试时打开
    # os.environ["LANGFUSE_DEBUG"] = "true"

    from langfuse import Langfuse

    Langfuse()  # v3 单例初始化


settings = AppSettings()
_sync_langsmith_env()
_init_langfuse()
```

---

## 4. 新建 `app/core/observability.py`（核心）

```python
"""Langfuse / LangChain 可观测性封装"""

from __future__ import annotations

from typing import Any

from app.core.settings import settings

_langfuse_handler = None


def get_langfuse_handler():
    """懒加载 CallbackHandler，未启用时返回 None"""
    global _langfuse_handler
    if not settings.langfuse_enabled:
        return None
    if _langfuse_handler is None:
        from langfuse.langchain import CallbackHandler

        _langfuse_handler = CallbackHandler()
    return _langfuse_handler


def langchain_config(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    给 LangChain / LangGraph 调用用的 config。
    metadata 里 langfuse_* 字段会出现在 Langfuse 面板。
    """
    config: dict[str, Any] = {}
    handler = get_langfuse_handler()
    if handler:
        config["callbacks"] = [handler]

    meta: dict[str, Any] = dict(metadata or {})
    if user_id:
        meta["langfuse_user_id"] = user_id
    if session_id:
        meta["langfuse_session_id"] = session_id
    if tags:
        meta["langfuse_tags"] = tags
    if meta:
        config["metadata"] = meta

    return config
```

---

## 5. 改 `rag_graph.py`（LangGraph RAG）

```python
from app.core.observability import langchain_config


async def run_rag(
    question: str,
    owner_ids: list[int] | None,
    *,
    user_id: int | None = None,
    session_id: int | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    config = langchain_config(
        user_id=str(user_id) if user_id else None,
        session_id=str(session_id) if session_id else None,
        tags=["rag"],
        metadata={"question": question[:200]},
    )
    result = await rag_graph.ainvoke(
        {"question": question, "owner_ids": owner_ids},
        config=config,
    )
    return result["answer"], result.get("chunks", [])
```

Langfuse 里会看到和 LangSmith 类似的树：

```
LangGraph
├── retrieve
└── generate
    └── ChatOpenAI
```

---

## 6. 改 `chat_service.py`

**非流式问答：**

```python
answer, chunks = await run_rag(
    question,
    owner_ids,
    user_id=user_id,          # 从 router 传下来
    session_id=session.id,
)
```

**流式问答：**

```python
from app.core.observability import langchain_config

async def stream_answer(
    question: str,
    owner_ids: list[int] | None,
    *,
    user_id: int | None = None,
    session_id: int | None = None,
) -> AsyncGenerator[str, None]:
    # ... 检索逻辑不变 ...

    config = langchain_config(
        user_id=str(user_id) if user_id else None,
        session_id=str(session_id) if session_id else None,
        tags=["rag", "stream"],
    )

    async for chunk in llm.astream(messages, config=config):
        if chunk.content:
            yield json.dumps({"type": "token", "content": chunk.content})
```

---

## 7. 改 `entity_extractor.py`（graph worker 也能追踪）

```python
from app.core.observability import langchain_config

def extract_and_store(...) -> None:
    llm = _get_llm()
    config = langchain_config(
        tags=["entity-extract"],
        metadata={"document_id": document_id, "chunk_id": chunk_id},
    )
    resp = llm.invoke(
        [
            SystemMessage(content=EXTRACT_PROMPT),
            HumanMessage(content=content[:2000]),
        ],
        config=config,
    )
    # ... 后面不变
```

**注意**：`graph_consumer` 也要能读到 `.env` 里的 `LANGFUSE_*`，并 import 到 `settings`（启动时会 `_init_langfuse()`）。

---

## 8. （可选）非 LLM 步骤也用 Langfuse 包一层

切片、召回这类 **不是 LangChain 调用**，用 `@observe`：

```python
# app/ai/retrievers/hybrid_retriever.py
from langfuse import observe

@observe(name="hybrid_retrieve")
async def hybrid_retrieve(db, question, owner_ids, top_k=None):
    bm25_hits = recall_bm25(...)
    vector_hits = await recall_pgvector(...)
    # ...
    return reranked[:top_k]
```

```python
# app/services/vector_service.py
from langfuse import observe

@observe(name="process_vector")
async def process_vector(document_id: int, db: AsyncSession) -> int:
    # MinIO → 切片 → embed → 写 PG/ES
    ...
```

这样在 Langfuse 里能看到 **切片/召回耗时**，这是 LangSmith 做不到的。

---

## 9. 本地自建 Langfuse（Docker）

官方 compose 较重（需要 Postgres + ClickHouse 等）。本地最快验证用 **Langfuse Cloud**；要自建可单独拉官方仓库：

```powershell
git clone https://github.com/langfuse/langfuse.git
cd langfuse
docker compose up -d
```

浏览器打开 `http://localhost:3000` → 注册 → 建项目 → 拿 `pk-lf-` / `sk-lf-` keys。

`.env` 里：

```env
LANGFUSE_ENABLED=true
LANGFUSE_BASE_URL=http://localhost:3000
```

---

## 10. 本地怎么验证（逐步）

### Step 1：确认 SDK 初始化

```powershell
python -c "from app.core.settings import settings; print(settings.langfuse_enabled, settings.langfuse_base_url)"
```

应输出 `True http://localhost:3000` 或 cloud URL。

### Step 2：确认 Langfuse 服务可达

```powershell
# 自建
curl http://localhost:3000/api/public/health

# Cloud 用浏览器打开 https://cloud.langfuse.com 能登录即可
```

### Step 3：重启 API，发一条 Chat

```powershell
uvicorn app.main:app --reload --port 8000
```

Swagger 或前端发：`POST /api/v1/chat/sessions/{id}/messages`

### Step 4：Langfuse 面板看 Trace

1. 打开 Langfuse → 你的项目  
2. 左侧 **Tracing** → **Traces**  
3. 几秒内应出现新 trace，tag 含 `rag`  
4. 点进去看：
   - **retrieve** / **generate** 节点
   - **generate → ChatOpenAI** 的 Input/Output（Prompt + 回复）
   - **Latency**、**Tokens**（如有）

### Step 5：流式 / 实体抽取（可选）

- 流式接口再发一条 → trace 带 `stream` tag  
- 跑 `graph_consumer` 处理文档 → trace 带 `entity-extract`

### Step 6：没 trace 时排查

| 现象 | 检查 |
|------|------|
| 完全没有 trace | `LANGFUSE_ENABLED=true`？keys 对不对？API 重启了吗？ |
| API 报错 | `pip show langfuse` 版本 ≥ 3.0 |
| worker 没 trace | worker 进程是否加载了同一 `.env` |
| 本地 Docker 连不上 | `LANGFUSE_BASE_URL` 是否 `http://localhost:3000`（不是 127.0.0.1 混用问题一般没事） |
| 调试 | `.env` 加 `LANGFUSE_DEBUG=true`，看终端日志 |

---

## 11. 上线后怎么验证

部署到服务器后，做一遍 **冒烟测试**：

```bash
# 1. 健康检查
curl https://your-api.com/health

# 2. 登录拿 token，发一条 chat（或用 Postman）
curl -X POST "https://your-api.com/api/v1/chat/sessions/1/messages" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"content":"公司请假流程是什么？"}'

# 3. 打开线上 Langfuse（如 https://langfuse.yourcompany.com）
#    → Traces → 按时间排序 → 确认刚才有新 trace
```

线上 `.env` 示例：

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-prod-xxx
LANGFUSE_SECRET_KEY=sk-lf-prod-xxx
LANGFUSE_BASE_URL=https://langfuse.yourcompany.com

LANGCHAIN_TRACING_V2=false   # 生产关 LangSmith
```

**验收标准**：
- Chat 后 30 秒内 Langfuse 有 trace  
- trace 里能看到完整 Prompt 和模型回复  
- `session_id` / `user_id` metadata 正确（方便按用户查）  
- 无 `401` / connection error 日志  

---

## 和 LangSmith 对比（你在面板上看什么）

| 面板位置 | LangSmith | Langfuse |
|----------|-----------|----------|
| 入口 | smith.langchain.com → Projects → Traces | Langfuse → Tracing → Traces |
| RAG 节点 | retrieve / generate | 同名（LangGraph callback） |
| LLM 详情 | generate → ChatOpenAI → Messages | 同上 → Input/Output |
| 切片/召回 | ❌ | ✅ 用 `@observe` 可加 |
| 按用户筛 | 需手动加 tag | `langfuse_user_id` / `langfuse_session_id` |

---

如果你确认要接，我可以直接帮你在项目里改这 4 个文件：`settings.py`、`observability.py`、`rag_graph.py`、`chat_service.py`（不动其他逻辑）。