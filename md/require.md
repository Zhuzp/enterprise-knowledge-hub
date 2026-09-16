项目整体是“核心 RAG 链路已有雏形，但语音、细粒度权限、线上观测和评估还没有落地”。逐项结论如下。

| 需求 | 状态 | 现状与缺口 |
|---|---|---|
| 1. PGVector + Elasticsearch 混合检索、RRF | 基本已实现 | [hybrid_retriever.py](D:/code/python/enterprise-knowledge-hub/app/ai/retrievers/hybrid_retriever.py) 同时调用 ES BM25 和 PGVector，并通过 [fusion.py](D:/code/python/enterprise-knowledge-hub/app/ai/retrievers/fusion.py) 做 RRF，之后还有 rerank。当前还额外融合了图谱召回。 |
| 2. Neo4j 知识图谱、LLM 抽取、多跳推理 | 部分实现 | 文档实体/关系抽取和写入 Neo4j 已有：[entity_extractor.py](D:/code/python/enterprise-knowledge-hub/app/ai/graph/entity_extractor.py)。但只处理前 3 个 chunk：[graph_service.py](D:/code/python/enterprise-knowledge-hub/app/services/graph_service.py)。用户问题不是通过 LLM 抽实体，而是使用 `$question CONTAINS e.name` 字符串匹配：[graph_reason.py](D:/code/python/enterprise-knowledge-hub/app/ai/agents/graph_reason.py)。多跳目前固定为 1~2 跳，推理结果和 chunk 已能合并进上下文。 |
| 3. 多格式解析、Markdown、MinIO、OCR/ASR/视频理解 | 部分实现 | PDF、DOCX、TXT/Markdown、图片、音频、视频解析器已存在；PDF/DOCX 图片会上传 MinIO 并替换成 URL。图片解析仍是明确 TODO，返回“`OCR 待实现`”：[image_parser.py](D:/code/python/enterprise-knowledge-hub/app/parsing/parsers/image_parser.py)。ASR 当前是 mock：[asr.py](D:/code/python/enterprise-knowledge-hub/app/parsing/providers/asr.py)。视频有分片、关键帧理解和音轨 ASR 流程，但 ASR 仍是 mock，且没有完整的媒体帧资产上传链路。PPTX/XLSX 测试文件存在，但当前 registry 不支持。 |
| 4. Redis 短期记忆 + Mem0 长期记忆 | 部分实现 | Redis 滑动窗口、摘要和 TTL 已实现：[short_term.py](D:/code/python/enterprise-knowledge-hub/app/ai/memory/short_term.py)。Mem0 用户级/会话级读写封装已实现：[long_term.py](D:/code/python/enterprise-knowledge-hub/app/ai/memory/long_term.py)，但 `mem0_enabled` 默认是 `False`，且 `requirements.txt` 没有 `mem0ai` 依赖，因此默认环境并未真正启用。 |
| 5. RBAC、页面/菜单/按钮权限、数据权限隔离 | 部分实现，缺口较大 | 已有用户、角色、用户角色、管理员校验，以及文档 owner/部门/public 过滤：[role.py](D:/code/python/enterprise-knowledge-hub/app/models/role.py)、[permission_service.py](D:/code/python/enterprise-knowledge-hub/app/services/permission_service.py)。但没有页面、菜单、按钮权限模型和对应拦截器，也没有文档级 ACL/角色授权表。当前主要是 `admin` 角色 + owner/department/public 规则，不能满足完整的三级功能权限和按角色分级保密。 |
| 6. LangGraph Agentic RAG | 基本已实现 | [agentic_rag_graph.py](D:/code/python/enterprise-knowledge-hub/app/ai/agents/agentic_rag_graph.py) 已有问题分析、复杂度判断、查询改写、混合检索、图谱推理和生成节点。当前更接近“预定义条件路由图”，不是可循环、自主规划/反思/重试的通用 Agent；工具集合也比较固定。 |
| 7. ASR + 流式 TTS + SSE + WebSocket | 仅实现 SSE | 聊天流式输出已经通过 `StreamingResponse` + `text/event-stream` 实现：[chat.py](D:/code/python/enterprise-knowledge-hub/app/api/v1/chat.py)。项目中没有 WebSocket 路由、TTS provider、流式音频协议或同步播放逻辑；ASR 也只是文档解析侧的 mock。 |
| 8. LangSmith、LangFuse、全链路观测、量化评估 | 部分/基本未实现 | LangSmith 只有环境变量同步配置：[settings.py](D:/code/python/enterprise-knowledge-hub/app/core/settings.py)，没有给 LangGraph/LLM 调用统一传入用户、会话、标签和 metadata。LangFuse 主要停留在设计文档：[langfuse.md](D:/code/python/enterprise-knowledge-hub/md/langfuse.md)，实际代码、依赖和 callback/observe 接入都没有完成。现有日志只有搜索次数和审计日志，缺少检索耗时、LLM token/cost、召回来源、模型异常等完整记录。没有发现 RAG/Agent 自动评估数据集、指标或实验 runner。 |

最主要的未实现项是：

1. 用户问题的 LLM 实体抽取。
2. 全量文档 chunk 的图谱抽取，而不是只处理前三个 chunk。
3. 图片 OCR 真正接通。
4. 真实 ASR 接口。
5. PPTX/XLSX 等格式支持。
6. 页面/菜单/按钮三级权限模型。
7. 文档级角色/用户 ACL。
8. WebSocket 流式 TTS。
9. LangFuse 实际接入。
10. RAG/Agent 自动化评估体系。

另外，当前 `requirements.txt` 也缺少至少这些生产能力对应的依赖：`mem0ai`、`langfuse`，以及可能使用的真实 ASR/TTS SDK。

总体判断：当前可以描述为“混合 RAG + 基础知识图谱 + Redis/Mem0 封装 + LangGraph 路由 + SSE 已完成原型”，还不能完整宣称 8 项需求全部落地。