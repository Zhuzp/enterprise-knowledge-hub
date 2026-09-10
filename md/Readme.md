**项目概述**
企业内部知识碎片化严重，跨部门资料无统一归集渠道，传统文档检索仅支持关键词匹配、无法回答需要跨文档推理的问题。为盘活企业知识资产、实现集中管理与高效复用，独立设计并开发了企业级知识库管理平台，包含文档管理、AI 问答、混合检索、知识图谱、RBAC 权限控制、数据统计与全链路可观测等模块。

**register**
客户端 POST /api/v1/auth/register
    ↓
FastAPI 路由匹配 (main.py → auth.py)
    ↓
Pydantic 校验请求体 (UserCreate)
    ↓
注入数据库会话 (get_db)
    ↓
register() 业务逻辑
    ├─ 查重 username / email
    ├─ hash_password()
    ├─ 创建 User ORM → db.add → flush → refresh
    └─ 返回 User 对象
    ↓
Pydantic 序列化 (UserResponse)
    ↓
get_db 自动 commit
    ↓
HTTP 201 + JSON 响应

**login**
客户端 POST /api/v1/auth/login
    ↓
FastAPI 路由匹配 (main.py → auth.py)
    ↓
Pydantic 校验请求体 (UserLogin)
    ↓
注入数据库会话 (get_db)
    ↓
login() 业务逻辑
    ├─ SELECT 按 username 查用户
    ├─ verify_password() 校验密码
    └─ create_access_token() 签发 JWT
    ↓
Pydantic 序列化 (Token)
    ↓
get_db 结束（本接口无写库，commit 空事务）
    ↓
HTTP 200 + access_token

**document上传**
客户端 POST /api/v1/documents (multipart/form-data + Bearer Token)
    ↓
FastAPI 路由匹配 (main.py → documents.py)
    ↓
鉴权 get_current_user() → 得到当前用户
    ↓
注入 get_db() → AsyncSession
    ↓
upload_document() 主逻辑
    ├─ validate_file()           扩展名校验
    ├─ visibility / department 校验
    ├─ file.read()               读入内存
    ├─ 文件大小校验
    ├─ generate_object_key()     生成 MinIO 路径
    ├─ upload_file()             上传到 MinIO
    ├─ Document ORM 写入 PG      status=pending_review
    ├─ write_audit_log()         审计日志
    └─ 失败时 delete_file()      清理 MinIO
    ↓
DocumentUploadResponse 序列化
    ↓
get_db 自动 commit
    ↓
HTTP 201 + 文档元数据

**publish**
管理员 POST /api/v1/review/{doc_id}  (action=approve)
    ↓
FastAPI 路由 (review.py)
    ↓
鉴权 get_current_admin() → 必须是 admin 角色
    ↓
review_one_document() 入口校验
    ↓
review_document() 审核业务
    ├─ 状态校验 pending_review
    ├─ 更新审核字段 + status=published (flush)
    ├─ publish_document_published() → RabbitMQ Fanout
    ├─ status=processing + 审计日志
    └─ flush + refresh
    ↓
DocumentReviewResponse 返回
    ↓
get_db commit

（异步，与 API 解耦）
RabbitMQ Fanout
    ├─ vector_consumer → process_vector()
    └─ graph_consumer  → process_graph()
    ↓
status=ready（向量和图谱都完成）

**文档发布后**
管理员 approve
    ↓
① 更新 PG（审核字段、status=processing）
② 发 RabbitMQ Fanout 消息
    ↓
    ├─ vector_consumer ──→ process_vector()
    │       MinIO 下载 → 解析 → 分块 → embedding → PG + ES
    │       vector_done = True
    │
    └─ graph_consumer ───→ process_graph()
            等 PG chunks → LLM 抽实体 → Neo4j
            graph_done = True
    ↓
vector_done && graph_done → status = ready（可搜索/RAG）

**检索**

**memory流程**
1. 用户提问 → 进入`build_memory_context`
2. **加载短期会话记忆**
   - 优先读 Redis；Redis 空就去 PG 查历史对话，并回填到 Redis
3. **加载长期记忆 Mem0**：向量库检索和当前问题相关的用户偏好记忆
4. 短期 + 长期记忆合并成`MemoryContext`，组装消息给大模型
5. LLM 输出答案返回前端
6. 保存本轮用户 + AI 消息到 Redis 滑动窗口
7. 判断对话条数是否太多：
   - 不多：无事发生
   - 太多：把老对话压缩成摘要、删掉窗口里老消息
8. 后台异步把对话写入 PG 做永久备份

**langgraph**


*需要的功能*
Reranker 模型重排，实现多路召回，提高检索准确率
1.向量+关键词(PGVector+ElasticSearch)实现混合检索，用RRF融合和
2.利用Neo4j构建知识图谱，通过LLM抽取文档实体、关系自动存入图数据库。用户问题会用LLM抽取实体，执行多跳检索，把推理链路和RAG的结果融合送入Prompt上下文，提升复杂业务问题回答的完整性与逻辑性
3.支持PDF、Word、TXT等图文格式文档，支持图片、音视频等多媒体文件，统一解析为Markdown文档，会自动提取文档中的图片上传到Minio，并替换文档中的图片为url。图片基于OCR实现解析、音频基于ASR、视频基于分片+视频理解模型解析成文
档。
4.Redis实现短期记忆存储(滑动窗口+摘要)，Mem0实现长期记忆分层存储，包括用户级、会话级记忆
5.基于RBAC模型搭建分层权限管控体系，落地页面、菜单、按钮三级细粒度权限拦截;同时联动检索逻辑做数据权限隔离，依据当前用户角色过滤文档池，不同人员仅可查询自身权限范围内的知识资料，实现功能权限与数据权限双重隔离，满足多部门资料分级保密需求。
6.基于 LangGraph实现Agentic RAG架构，Agent 自主判别问题复杂度，动态决策调用混合检索、图谱推理等工具，灵活适配多维度复杂业务提问，规避固定检索流程带来的回答局限性:
7.基于ASR+流式TTS实现语音交互，SSE实现文字流式输出，WebSocket+流式
TTS实现语音的同步流式播放。
8.本地开发用LangSmith调试，线上用LangFuse收集数据，实现全链路观测，记录检
索耗时、LLM调用成本、问答召回来源、模型报错日志等。搭建RAG和Agent效果量
化评估机制，自动跑实验来评估检索效果。

**项目启动指令**
# 终端 1
cd D:\code\python\enterprise-knowledge-hub
docker compose up -d postgres redis minio elasticsearch neo4j rabbitmq

# 终端 2
cd D:\code\python\enterprise-knowledge-hub
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# 终端 3~6（需要文档全流程时）
.\.venv\Scripts\Activate.ps1
python -m app.workers.parse_consumer --queue document.parse.light.queue
# 新开终端
python -m app.workers.parse_consumer --queue document.parse.heavy.queue
python -m app.workers.vector_consumer
python -m app.workers.graph_consumer

**数据库迁移指令**
alembic revision -m "add document parse fields"
alembic upgrade head
alembic current

文档接入、异步解析、索引和权限隔离；
混合检索、重排、引用溯源；
一套小型评测集，能比较不同切分、召回、Rerank 策略；
Trace、Token 成本、失败重试、人工兜底；
Docker Compose 一键启动、README、架构图和接口文档。