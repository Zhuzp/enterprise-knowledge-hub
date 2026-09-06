很好，项目已经跑起来了。下面按 **Python 新手友好** 的方式拆解，每一步都尽量小、能单独验证。

你现在的结构是：

```
enterprise-knowledge-hub/
├── app/
│   └── main.py          # FastAPI 入口
├── requirements.txt
└── .venv/
```

启动命令（在项目根目录）：

```powershell
uvicorn app.main:app --reload
```

---

## 总体路线图

```
阶段0  熟悉 FastAPI 基础          ← 你现在在这里
阶段1  项目骨架 + 配置
阶段2  数据库 + 用户登录
阶段3  文档上传
阶段4  文档解析 + 搜索
阶段5  AI 问答
阶段6  权限 + 统计 + 打磨
```

**原则：** 每完成一个小任务就测试一次，不要一次写太多。

---

## 阶段 0：先搞懂你现在这段代码（半天）

### 任务 0.1：理解 `main.py`

```python
from fastapi import FastAPI   # 导入框架

app = FastAPI(...)            # 创建应用实例

@app.get("/health")           # 装饰器：注册 GET 路由
def health():                 # 处理函数
    return {"status": "ok"}     # 返回 JSON
```

你需要理解 3 个概念：

| 概念 | 含义 |
|------|------|
| `import` | 引入别人写好的库 |
| `@app.get(...)` | 装饰器，把函数注册成接口 |
| `return {...}` | 返回字典，FastAPI 自动转成 JSON |

### 任务 0.2：加 2 个接口练手

在 `main.py` 里加：

```python
@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"你好, {name}"}

@app.post("/echo")
def echo(data: dict):
    return {"you_sent": data}
```

验证：
- 浏览器打开 http://127.0.0.1:8000/hello/张三
- 打开 http://127.0.0.1:8000/docs ，在 Swagger 里试 POST `/echo`

**学会：** 路径参数、POST 请求、自动 API 文档。

---

## 阶段 1：搭项目骨架（1–2 天）

目标：代码不要全堆在 `main.py`，按模块拆分。

### 任务 1.1：创建目录结构

在 `app/` 下新建：

```
app/
├── main.py              # 只负责启动和注册路由
├── core/
│   └── config.py        # 读取配置（数据库地址等）
├── api/
│   └── v1/
│       └── health.py    # 健康检查接口
├── schemas/             # 请求/响应的数据格式
├── models/              # 数据库表定义（后面用）
├── services/            # 业务逻辑
└── infra/               # 数据库、Redis 等连接
```

每个文件夹里放一个空的 `__init__.py`（Python 把它识别为包）。

> **Python 知识点：** `__init__.py` 让文件夹变成可 `import` 的模块。

### 任务 1.2：写配置文件

`app/core/config.py`：

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
  app_name: str = "Enterprise Knowledge Hub"
  database_url: str = "postgresql://user:pass@localhost:5432/knowledge"
  redis_url: str = "redis://localhost:6379/0"

  class Config:
    env_file = ".env"   # 从 .env 文件读配置

settings = Settings()
```

项目根目录建 `.env`：

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/knowledge
REDIS_URL=redis://localhost:6379/0
```

安装依赖：

```powershell
pip install pydantic-settings
```

### 任务 1.3：拆分路由

`app/api/v1/health.py`：

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}
```

`app/main.py`：

```python
from fastapi import FastAPI
from app.api.v1.health import router as health_router

app = FastAPI(title="Enterprise Knowledge Hub")
app.include_router(health_router, prefix="/api/v1")
```

验证：http://127.0.0.1:8000/api/v1/health 能访问。

**学会：** 模块化、`import`、路由拆分。

### 任务 1.4：Docker 拉起数据库

根目录建 `docker-compose.yml`，先只起 PostgreSQL + Redis：

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: knowledge
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    ports:
      - "6379:6379"
```

```powershell
docker compose up -d
```

**验收：** `docker compose ps` 看到两个服务在运行。

---

## 阶段 2：用户注册登录（2–3 天）

目标：能注册、登录、拿 Token。

### 任务 2.1：连接数据库

安装：

```powershell
pip install sqlalchemy asyncpg alembic
```

`app/infra/db.py` — 创建数据库连接。

`app/models/user.py` — 定义用户表：

```python
# 字段：id, username, email, hashed_password, created_at
```

> **Python 知识点：** SQLAlchemy 的 `Column`、`String`、`DateTime` 类似 Java 的 JPA Entity。

### 任务 2.2：数据库迁移

```powershell
alembic init alembic
# 配置 alembic.ini 里的数据库地址
alembic revision --autogenerate -m "create users table"
alembic upgrade head
```

**验收：** PostgreSQL 里能看到 `users` 表。

### 任务 2.3：注册接口

`app/schemas/user.py` — 定义请求/响应格式：

```python
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
```

`app/api/v1/auth.py`：

| 接口 | 功能 |
|------|------|
| `POST /api/v1/auth/register` | 注册 |
| `POST /api/v1/auth/login` | 登录，返回 JWT |
| `GET /api/v1/auth/me` | 获取当前用户（需 Token） |

安装：

```powershell
pip install python-jose passlib bcrypt
```

> **Python 知识点：**
> - `Pydantic BaseModel` = 数据校验（类似 DTO）
> - `async def` = 异步函数（数据库操作用）
> - `Depends()` = 依赖注入（类似 Spring 的 `@Autowired`）

**验收：** 在 `/docs` 里注册 → 登录 → 拿 Token → 访问 `/me`。

---

## 阶段 3：文档上传（2–3 天）

目标：登录后能上传 PDF/Word，文件存 MinIO。

### 任务 3.1：MinIO 加入 docker-compose

```yaml
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
```

安装：`pip install minio`

`app/infra/minio_client.py` — 封装上传/下载。

### 任务 3.2：文档表

`app/models/document.py`：

```
documents 表：
  id, title, file_name, file_size, minio_key,
  owner_id, status(pending/processing/ready), created_at
```

### 任务 3.3：上传接口

`POST /api/v1/documents`：

```python
@router.post("/documents")
async def upload_document(
    file: UploadFile,           # FastAPI 接收文件
    current_user = Depends(get_current_user)
):
    # 1. 校验文件类型和大小
    # 2. 上传到 MinIO
    # 3. 写数据库记录
    # 4. 返回文档信息
```

| 接口 | 功能 |
|------|------|
| `POST /documents` | 上传 |
| `GET /documents` | 我的文档列表 |
| `GET /documents/{id}` | 文档详情 |
| `DELETE /documents/{id}` | 删除 |

**验收：** 上传一个 PDF，MinIO 控制台（http://localhost:9001）能看到文件，数据库有记录。

---

## 阶段 4：文档解析 + 搜索（3–5 天）

目标：上传的文档能被搜索到。

### 任务 4.1：异步任务（文档解析）

安装：`pip install arq`（轻量异步任务队列）

流程：

```
上传完成 → 往 Redis 丢一个任务 → Worker 后台执行：
  1. 从 MinIO 下载文件
  2. 用 pypdf / python-docx 解析文本
  3. 分块（每块约 500 字）
  4. 存入 document_chunks 表
  5. 触发索引任务
```

安装：`pip install pypdf python-docx`

> **Python 知识点：** `arq` worker 是一个独立进程，用 `python -m arq app.workers.settings` 启动。

### 任务 4.2：ElasticSearch 搜索

docker-compose 加 Elasticsearch。

安装：`pip install elasticsearch`

`POST /api/v1/search?q=年假` — 关键词搜索文档。

**验收：** 上传一份含「年假 10 天」的 PDF，搜索「年假」能搜到。

---

## 阶段 5：AI 问答（3–5 天，核心亮点）

目标：能问问题，AI 基于文档回答并引用来源。

### 任务 5.1：向量检索

安装：`pip install langchain langchain-openai elasticsearch`

文档分块后 → 调用 OpenAI Embedding API → 向量存入 ES。

### 任务 5.2：简单 RAG

先不用 LangGraph，写一个最简单的版本：

```python
def ask(question: str, user_id: int) -> str:
    # 1. 搜索相关文档块（ES）
  # 2. 拼成 prompt
    # 3. 调 LLM 生成答案
    # 4. 返回答案 + 引用来源
```

### 任务 5.3：流式问答接口

`POST /api/v1/chat/messages` — SSE 流式返回。

安装：`pip install langgraph`（后面升级用）

### 任务 5.4：会话管理

```
qa_sessions 表：id, user_id, title, created_at
qa_messages 表：id, session_id, role, content, citations
```

**验收：** 问「年假有几天？」，返回答案 + 「来源：员工手册 第3页」。

---

## 阶段 6：进阶功能（按需）

| 任务 | 难度 | 说明 |
|------|------|------|
| 权限控制 | ⭐⭐ | 部门隔离、文档 ACL |
| 知识图谱 Neo4j | ⭐⭐⭐ | 实体抽取 + 关系可视化 |
| LangGraph 工作流 | ⭐⭐⭐ | 多步推理、意图路由 |
| Mem0 记忆 | ⭐⭐ | 记住用户偏好 |
| 数据统计 | ⭐ | 上传量、搜索热词 |
| LangFuse 监控 | ⭐⭐ | Token 用量、延迟追踪 |

---

## 每周计划（单人）

| 周 | 做什么 | 产出 |
|----|--------|------|
| **第1周** | 阶段 0 + 1 + 2 | 项目骨架 + 用户登录 |
| **第2周** | 阶段 3 | 文档上传 + MinIO |
| **第3周** | 阶段 4 | 解析 + ES 搜索 |
| **第4周** | 阶段 5 | AI 问答（最大亮点） |
| **第5周** | 阶段 6 | 权限 + 统计 + README |

---

## Python 新手常见坑

| 坑 | 正确做法 |
|----|----------|
| `import` 报错 | 确保文件夹有 `__init__.py`，从项目根目录启动 |
| 改了代码不生效 | 确认 `--reload` 开着，或手动重启 |
| 虚拟环境没激活 | 终端前面应有 `(.venv)` |
| `async` 函数里调同步代码 | 数据库操作用 `async def` + `await` |
| 路径问题 | 始终在**项目根目录**运行 `uvicorn app.main:app` |

---

## 建议你现在做的第一件事

**阶段 1 的任务 1.1 + 1.3**：把 `main.py` 拆成模块化结构。

完成后你的项目会变成：

```
app/
├── main.py
├── core/config.py
└── api/v1/health.py
```

这是后面所有功能的基础。

---

你想从哪个任务开始？我可以直接在项目里帮你写 **阶段 1 的骨架代码**（目录结构 + config + 路由拆分），你跟着跑起来再往下做。