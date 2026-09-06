下面把企业知识库项目拆成 **Python 技术栈 + 可执行的开发计划**。整体思路是：**FastAPI 做业务中台，LangGraph 做 AI 编排，先跑通 MVP，再逐步加图谱和高级 Agent**。

---

## 一、Python 技术栈选型

| 原方案 | Python 替代 | 说明 |
|--------|-------------|------|
| NestJS | **FastAPI** | 异步、OpenAPI 自动生成、和 AI 生态契合 |
| Vercel AI SDK | **Next.js 前端 + SSE** 或 **FastAPI StreamingResponse** | 后端用 Python 流式输出，前端单独用 React/Next |
| LangChain / LangGraph | 同名 Python 库 | 原生支持 |
| DeepAgents | Python 版 | Agent 多步推理 |
| PostgreSQL | **SQLAlchemy 2.0 + Alembic** | ORM + 迁移 |
| Redis | **redis-py / arq / Celery** | 缓存 + 异步任务 |
| ElasticSearch | **elasticsearch-py** | 全文 + 向量检索 |
| Neo4j | **neo4j Python driver** | 图谱 |
| MinIO | **minio-py** | 对象存储 |
| Mem0 | **mem0ai** Python SDK | 用户记忆 |
| LangSmith / LangFuse | 官方 Python SDK | 可观测 |

**推荐基础依赖：**
```txt
fastapi uvicorn[standard]
sqlalchemy alembic asyncpg
redis arq                    # 或 celery
elasticsearch
neo4j
minio
langchain langchain-community langgraph
mem0ai
langsmith langfuse
python-jose passlib          # JWT + 密码
pypdf python-docx unstructured  # 文档解析
sentence-transformers        # 本地 embedding（可选）
httpx pydantic-settings
```

---

## 二、项目目录结构

```
enterprise-knowledge-hub/
├── docker-compose.yml          # PG / Redis / ES / Neo4j / MinIO
├── .env.example
├── pyproject.toml              # 或 requirements.txt
│
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── core/
│   │   ├── config.py           # 配置
│   │   ├── security.py         # JWT / 密码
│   │   └── deps.py             # 依赖注入
│   │
│   ├── models/                 # SQLAlchemy 模型
│   │   ├── user.py
│   │   ├── document.py
│   │   └── permission.py
│   │
│   ├── schemas/                # Pydantic DTO
│   ├── api/
│   │   ├── v1/
│   │   │   ├── auth.py
│   │   │   ├── documents.py
│   │   │   ├── search.py
│   │   │   ├── chat.py
│   │   │   ├── graph.py
│   │   │   └── stats.py
│   │
│   ├── services/               # 业务逻辑
│   │   ├── document_service.py
│   │   ├── search_service.py
│   │   ├── permission_service.py
│   │   └── stats_service.py
│   │
│   ├── ai/                     # AI 子系统
│   │   ├── loaders/            # PDF/Word/MD 加载
│   │   ├── splitters/          # 分块策略
│   │   ├── embeddings/         # 向量化
│   │   ├── retrievers/         # ES 检索器
│   │   ├── graph/              # 实体抽取 + Neo4j
│   │   ├── agents/
│   │   │   ├── rag_graph.py    # LangGraph RAG 工作流
│   │   │   └── deep_agent.py   # DeepAgents 复杂任务
│   │   └── memory/             # Mem0 封装
│   │
│   ├── workers/                # 异步任务
│   │   ├── parse_document.py   # 文档解析入库
│   │   └── index_document.py   # ES 索引 + embedding
│   │
│   └── infra/                  # 基础设施客户端
│       ├── db.py
│       ├── redis_client.py
│       ├── es_client.py
│       ├── neo4j_client.py
│       └── minio_client.py
│
├── alembic/                    # 数据库迁移
├── tests/
└── frontend/                   # 可选：Next.js 问答界面
```

---

## 三、分阶段拆解（4 个 Sprint）

### Sprint 0：基础设施（3–5 天）

**目标：** 所有中间件跑起来，FastAPI 骨架可用。

| 任务 | 产出 |
|------|------|
| 写 `docker-compose.yml` | PostgreSQL、Redis、ES、Neo4j、MinIO 一键启动 |
| 初始化 FastAPI 项目 | `/health` 接口、配置加载、日志 |
| SQLAlchemy + Alembic | 用户、部门、角色基础表 |
| 封装 infra 客户端 | db / redis / es / minio / neo4j 单例 |

**验收：** `docker compose up` 后，`GET /health` 返回 ok，能连上所有服务。

---

### Sprint 1：文档管理 + 权限（1–2 周）

**目标：** 能上传文档、存 MinIO、记元数据、控权限。

#### 1.1 用户与权限
```
users, roles, departments, user_roles
documents (id, title, dept_id, owner_id, status, minio_key)
document_permissions (doc_id, subject_type, subject_id, level)
```

| 接口 | 方法 | 功能 |
|------|------|------|
| `/auth/register` | POST | 注册 |
| `/auth/login` | POST | JWT 登录 |
| `/users/me` | GET | 当前用户 |
| `/documents` | POST | 上传文档 |
| `/documents` | GET | 列表（带权限过滤） |
| `/documents/{id}` | GET | 详情 / 下载 |
| `/documents/{id}` | DELETE | 软删除 |

**核心逻辑：**
- 上传 → MinIO 存原文件 → PG 写元数据 → 发异步解析任务
- 权限：`owner` / `dept:read` / `role:admin` / 文档级 ACL

#### 1.2 异步解析 Worker
```
上传完成
  → Redis 队列
  → Worker 拉取
  → 解析 PDF/Word/MD
  → 分块 chunk
  → 写 document_chunks 表
  → 触发索引任务（Sprint 2）
```

**验收：** 上传 PDF 后，数据库有 chunks，MinIO 有原文件。

---

### Sprint 2：全文搜索 + RAG 问答（1–2 周）

**目标：** 能搜文档、能 AI 问答并引用来源。这是简历最大亮点。

#### 2.1 ElasticSearch 索引设计
```json
{
  "doc_id": "uuid",
  "chunk_id": "uuid",
  "title": "员工手册",
  "content": "chunk 文本",
  "dept_id": "xxx",
  "embedding": [0.1, 0.2, ...],
  "metadata": { "page": 3, "section": "请假制度" }
}
```

| 任务 | 说明 |
|------|------|
| 建立 ES index mapping | text + dense_vector |
| 索引 Worker | chunk → embedding → bulk index |
| 关键词检索 | `match` query |
| 向量检索 | kNN search |
| 混合检索 | BM25 + 向量加权融合 |
| 权限过滤 | ES `filter` 限定可见 `doc_id` |

#### 2.2 LangGraph RAG 工作流

```python
# 简化流程
START
  → classify_intent      # 简单查询 / 复杂分析
  → retrieve             # ES hybrid search
  → rerank               # 取 Top-K
  → generate             # LLM 生成 + 引用
  → (optional) validate  # 答案是否 grounded
END
```

| 接口 | 方法 | 功能 |
|------|------|------|
| `/search` | GET | 关键词/语义搜索 |
| `/chat/sessions` | POST | 创建会话 |
| `/chat/sessions/{id}/messages` | POST | 提问（SSE 流式） |
| `/chat/sessions/{id}/messages` | GET | 历史消息 |

**接入：**
- **LangSmith**：记录每次 retrieve + generate trace
- **LangFuse**：生产监控、token 成本
- **Mem0**：记住用户常问领域（可选，Sprint 3 加）

**验收：** 问「年假几天？」能返回答案 + 引用文档片段。

---

### Sprint 3：知识图谱 + DeepAgents（1–2 周）

**目标：** 复杂关联查询、多步任务。

#### 3.1 知识图谱
```
文档 chunk
  → LLM 抽取实体/关系
  → 写入 Neo4j
  
(Person)-[:AUTHORED]->(Document)
(Department)-[:OWNS]->(Document)
(Policy)-[:REFERENCES]->(Policy)
```

| 接口 | 功能 |
|------|------|
| `/graph/entities` | 实体列表 |
| `/graph/relations` | 关系查询 |
| `/graph/visualize` | 子图数据（给前端渲染） |

**RAG 增强：** 检索时先从 Neo4j 扩展关联实体，再回 ES 查文档。

#### 3.2 DeepAgents 复杂任务
适合场景：
- 「对比 A 部门和 B 部门的报销制度差异」
- 「汇总某项目所有相关文档并写摘要」

```
用户问题
  → DeepAgent 拆解子任务
  → 子任务1: 搜索文档A
  → 子任务2: 搜索文档B
  → 子任务3: 对比分析
  → 汇总输出
```

**验收：** 问关联型问题，图谱能扩展召回；多步任务能自动拆解。

---

### Sprint 4：数据统计 + 打磨（3–5 天）

| 模块 | 指标 |
|------|------|
| 文档统计 | 总量、各部门占比、上传趋势 |
| 搜索统计 | 热词 Top10、零结果查询 |
| 问答统计 | 会话数、平均响应时间、引用率 |
| 用户行为 | 活跃用户、高频文档 |

| 接口 | 功能 |
|------|------|
| `/stats/overview` | 总览仪表盘 |
| `/stats/search-hotwords` | 检索热词 |
| `/stats/qa-quality` | 问答质量（LangFuse 聚合） |

**额外打磨：**
- 审计日志（谁看了什么文档）
- 限流（Redis 令牌桶）
- Docker 生产 compose
- README + 架构图

---

## 四、核心模块代码职责（便于分工）

### 1. `app/services/document_service.py`
- 上传校验（类型、大小）
- MinIO 存储
- 触发 parse job
- 权限校验

### 2. `app/workers/parse_document.py`
- 用 `unstructured` / `pypdf` 解析
- RecursiveCharacterTextSplitter 分块
- 持久化 chunks

### 3. `app/ai/retrievers/hybrid_retriever.py`
- 接收 query + user_id
- 查用户可见 doc_ids
- ES BM25 + kNN
- 返回 Top-K chunks

### 4. `app/ai/agents/rag_graph.py`
- LangGraph StateGraph
- 节点：intent → retrieve → rerank → generate
- 流式 yield token

### 5. `app/ai/graph/entity_extractor.py`
- LLM structured output 抽实体关系
- 批量写 Neo4j

### 6. `app/services/permission_service.py`
- `get_accessible_doc_ids(user_id)` 
- RAG/搜索的前置过滤器

---

## 五、数据库表（最小集）

```sql
-- 用户权限
users, roles, departments, user_roles

-- 文档
documents, document_versions, document_chunks

-- 权限
document_permissions

-- 问答
qa_sessions, qa_messages  -- messages 存 citations JSON

-- 日志
search_logs, audit_logs
```

---

## 六、Docker Compose 服务清单

```yaml
services:
  postgres:     # 5432
  redis:        # 6379
  elasticsearch:# 9200
  neo4j:        # 7474 / 7687
  minio:        # 9000
  api:          # FastAPI 8000
  worker:       # arq/celery worker
```

---

## 七、MVP 最小范围（1 周可 demo）

如果时间紧，**第一版只做这些**：

1. FastAPI + PostgreSQL + MinIO + Redis
2. 用户登录 + 文档上传
3. 异步解析 + ES 关键词搜索
4. LangGraph 简单 RAG 问答（流式 + 引用）
5. Docker Compose 一键启动

**暂缓：** Neo4j 图谱、DeepAgents、Mem0、LangFuse 仪表盘

这样已经够写简历，后面再迭代。

---

## 八、建议开发顺序（单人）

```
Week 1: Docker + FastAPI + 用户/auth + 文档上传
Week 2: 解析 Worker + ES 索引 + 搜索接口
Week 3: LangGraph RAG + SSE 流式问答
Week 4: 权限完善 + 统计 + README
Week 5+: Neo4j 图谱 + DeepAgents + Mem0
```

---

## 九、简历可写的 Python 版职责

> - 基于 **FastAPI** 设计 RESTful API，SQLAlchemy 管理 PostgreSQL 元数据，MinIO 存储原始文档  
> - 使用 **arq/Celery** 实现文档异步解析与 ES 索引流水线，支持 PDF/Word/Markdown 多格式  
> - 基于 **LangChain + LangGraph** 构建 Hybrid RAG 工作流，ElasticSearch 实现 BM25 + 向量混合检索  
> - 集成 **Neo4j** 做实体关系抽取与图谱增强召回，**DeepAgents** 处理多步分析任务  
> - 接入 **LangSmith/LangFuse** 做全链路追踪，**Mem0** 实现用户级对话记忆  

---

如果你愿意，我下一步可以直接帮你在 `d:\code` 里 **scaffold 项目骨架**（docker-compose + FastAPI 目录 + 基础模型 + 第一个上传接口）。你想从 **MVP（Week 1）** 还是 **完整骨架** 开始？