很好，阶段 5 已经接上了。下面按**从整体到细节**说明每段代码在做什么、起什么作用。

---

## 一、阶段 5 解决什么问题？

阶段 4 只能**搜文档片段**，阶段 5 能**像 ChatGPT 一样问答**：

```
用户：「年假有几天？」
  ↓
系统：「根据《员工手册》，员工每年享有年假 10 天。」
      引用来源：《员工手册》第 3 页
```

核心技术叫 **RAG（Retrieval-Augmented Generation）**：

```
R = Retrieval（检索）  → 从 ES 找相关文档
A = Augmented（增强）   → 把文档塞进 Prompt
G = Generation（生成）  → LLM 基于资料生成回答
```

---

## 二、整体架构

```
┌─────────────┐
│  chat.py    │  HTTP 接口（5 个 API）
└──────┬──────┘
       ↓
┌─────────────┐
│chat_service │  会话管理、保存消息
└──────┬──────┘
       ↓
┌─────────────┐
│ rag_graph   │  LangGraph：retrieve → generate
└──────┬──────┘
       ↓
┌─────────────┬─────────────┐
│ es_client   │  OpenAI API │
│ retrieve    │  ChatOpenAI │
└─────────────┴─────────────┘
```

| 文件 | 层级 | 职责 |
|------|------|------|
| `models/chat.py` | 数据 | 会话表 + 消息表 |
| `schemas/chat.py` | 接口格式 | 请求/响应 DTO |
| `es_client.retrieve_chunks` | 基础设施 | ES 检索（阶段 4 扩展） |
| `ai/rag_graph.py` | AI 核心 | LangGraph RAG 工作流 |
| `services/chat_service.py` | 业务 | 会话逻辑 + 调用 RAG |
| `api/v1/chat.py` | 接口 | 5 个 HTTP 端点 |

---

## 三、和阶段 4 的关系

```
阶段 4 搜索：GET /search?q=年假
  → 返回 chunk 列表（原始片段）

阶段 5 问答：POST /chat/sessions/1/messages
  → 内部也调 retrieve_chunks（同一套 ES 索引）
  → 但多了一步 LLM 生成自然语言回答
  → 还保存了会话历史
```

| | 阶段 4 搜索 | 阶段 5 问答 |
|--|------------|------------|
| 返回 | 文档片段列表 | 自然语言 + 引用 |
| 理解能力 | 关键词匹配 | LLM 语义理解 |
| 会话 | 无 | 有历史记录 |
| 问「带薪休假几天」 | 可能搜不到 | LLM 可理解并回答 |

---

## 四、逐文件讲解

### 1. `models/chat.py` — 会话数据表

```10:38:d:\code\python\enterprise-knowledge-hub\app\models\chat.py
class QASession(Base):
    __tablename__ = "qa_sessions"
    id, user_id, title, created_at
    messages = relationship(..., cascade="all, delete-orphan")

class QAMessage(Base):
    __tablename__ = "qa_messages"
    id, session_id, role, content, citations, created_at
```

**两张表的关系：**

```
qa_sessions（一个对话）
  ├── qa_messages（role=user）   「年假有几天？」
  └── qa_messages（role=assistant）「根据手册，10天」+ citations JSON
```

| 字段 | 作用 |
|------|------|
| `QASession.title` | 对话标题，首问自动截取前 50 字 |
| `QAMessage.role` | `user` 或 `assistant` |
| `QAMessage.citations` | JSONB，仅存 assistant 的引用来源 |
| `cascade="all, delete-orphan"` | 删会话时自动删所有消息 |

**类比：** `QASession` = ChatGPT 左侧一个对话；`QAMessage` = 对话里的每条消息。

---

### 2. `schemas/chat.py` — API 数据格式

```6:47:d:\code\python\enterprise-knowledge-hub\app\schemas\chat.py
class Citation(BaseModel): ...
class ChatSessionCreate(BaseModel): ...
class ChatSessionResponse(BaseModel): ...
class ChatMessageCreate(BaseModel): ...
class ChatMessageResponse(BaseModel): ...
class ChatAnswerResponse(BaseModel): ...
```

| 类 | 用于 | 关键字段 |
|----|------|----------|
| `Citation` | 单条引用 | document_id, title, snippet, score |
| `ChatSessionCreate` | 创建会话 | title（默认「新对话」） |
| `ChatMessageCreate` | 提问 | question（1~2000 字） |
| `ChatAnswerResponse` | 一问一答完整响应 | answer + citations + 两条 message |

**`ChatAnswerResponse` 为什么同时返回 answer 和两条 message？**

- `answer`：方便前端直接展示
- `user_message` / `assistant_message`：带 id、时间，便于刷新历史

---

### 3. `es_client.retrieve_chunks` — RAG 检索入口

```89:116:d:\code\python\enterprise-knowledge-hub\app\infra\es_client.py
def retrieve_chunks(query, owner_id, top_k=5) -> list[dict]:
    # ES bool 查询：match content + filter owner_id
    # 返回 Top-K chunk，每条含 document_id, chunk_id, title, content, score
```

| 和 `search_documents` 的区别 | retrieve_chunks | search_documents |
|------------------------------|-----------------|------------------|
| 用途 | 给 LLM 当上下文 | 给用户看搜索结果 |
| 条数 | 固定 Top-K（5 条） | 分页 |
| 高亮 | 无 | 有 `<em>` 高亮 |
| 返回 | `list[dict]` | ES 原始 JSON |

**`owner_id` 过滤：** 只检索当前用户自己的文档，避免看到别人资料。

---

### 4. `ai/rag_graph.py` — 核心：LangGraph RAG 工作流

这是阶段 5 的**大脑**。

#### 4.1 System Prompt

```12:14:d:\code\python\enterprise-knowledge-hub\app\ai\rag_graph.py
SYSTEM_PROMPT = """你是企业内部知识库助手。请仅根据提供的参考资料回答问题。
如果参考资料中没有相关信息，请明确说「根据现有资料无法回答」，不要编造。
回答请简洁、准确，使用中文。"""
```

| 要求 | 作用 |
|------|------|
| 仅根据参考资料 | 防幻觉（编造） |
| 没有就说无法回答 | 资料外问题不乱答 |
| 中文简洁 | 控制输出风格 |

#### 4.2 状态定义 `RAGState`

```17:22:d:\code\python\enterprise-knowledge-hub\app\ai\rag_graph.py
class RAGState(TypedDict):
    question: str      # 用户问题
    owner_id: int      # 谁问的（用于检索过滤）
    chunks: list[dict] # 检索到的原始 chunk
    context: str       # 拼好的参考资料文本
    answer: str        # LLM 最终回答
```

LangGraph 用 **State** 在节点间传递数据，每个节点读 state、返回要更新的字段。

#### 4.3 节点 1：`retrieve_node` — 检索

```34:47:d:\code\python\enterprise-knowledge-hub\app\ai\rag_graph.py
def retrieve_node(state: RAGState) -> dict:
    chunks = retrieve_chunks(state["question"], state["owner_id"], settings.rag_top_k)
    if not chunks:
        return {"chunks": [], "context": "", "answer": "未找到相关文档..."}

    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(f"[{i}] 文档《{c['title']}》\n{c['content']}")
    context = "\n\n".join(parts)
    return {"chunks": chunks, "context": context}
```

**执行逻辑：**

```
输入: question="年假几天", owner_id=1
  ↓
ES 检索 Top-5 chunk
  ↓
没结果 → 直接设 answer="未找到相关文档"（后面 generate 会跳过 LLM）
有结果 → 拼成:
  [1] 文档《员工手册》
  员工每年享有年假 10 天...

  [2] 文档《考勤制度》
  年假需提前 3 天申请...
```

**`[1]`、`[2]` 编号：** 方便 LLM 引用，也方便转成 citations。

#### 4.4 节点 2：`generate_node` — 生成

```50:62:d:\code\python\enterprise-knowledge-hub\app\ai\rag_graph.py
def generate_node(state: RAGState) -> dict:
    if not state.get("context"):
        return {"answer": state.get("answer", "未找到相关文档。")}

    llm = _get_llm()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"参考资料：\n{state['context']}\n\n用户问题：{state['question']}"),
    ]
    response = llm.invoke(messages)
    return {"answer": response.content}
```

**发给 LLM 的完整 Prompt 结构：**

```
[System] 你是企业知识库助手，仅根据参考资料回答...

[Human]  参考资料：
         [1] 文档《员工手册》
         员工每年享有年假 10 天...

         用户问题：年假有几天？
```

| 细节 | 作用 |
|------|------|
| `context` 为空时跳过 LLM | 省 API 费用，避免无资料还编造 |
| `temperature=0.2` | 偏低，回答更稳定、少随机 |
| `invoke` | 同步等 LLM 返回完整回答 |

#### 4.5 图的组装

```65:80:d:\code\python\enterprise-knowledge-hub\app\ai\rag_graph.py
graph.add_node("retrieve", retrieve_node)
graph.add_node("generate", generate_node)
graph.add_edge(START, "retrieve")
graph.add_edge("retrieve", "generate")
graph.add_edge("generate", END)

def run_rag(question, owner_id):
    result = rag_graph.invoke({"question": question, "owner_id": owner_id})
    return result["answer"], result.get("chunks", [])
```

**流程图：**

```
START → retrieve → generate → END
```

**为什么用 LangGraph 而不是直接写函数？**

- 现在只有 2 步，直接调用也行
- 阶段 6 可加节点：意图识别、重排序、答案校验、多步推理
- 简历可写「LangGraph 编排 RAG 工作流」

**State 变化示例：**

```
invoke 输入:
  { question: "年假几天", owner_id: 1 }

retrieve 之后:
  { ..., chunks: [...], context: "[1] 文档《员工手册》..." }

generate 之后:
  { ..., answer: "根据员工手册，年假为 10 天" }

run_rag 返回:
  ("根据员工手册，年假为 10 天", [chunk1, chunk2, ...])
```

---

### 5. `services/chat_service.py` — 业务编排

#### 5.1 `chunks_to_citations` — 格式转换

```16:29:d:\code\python\enterprise-knowledge-hub\app\services\chat_service.py
def chunks_to_citations(chunks):
    # ES chunk dict → Citation 对象
    # snippet 截取 content 前 200 字
```

把 ES 原始 chunk 转成前端友好的 `Citation`，snippet 只取前 200 字。

#### 5.2 会话 CRUD

| 函数 | 作用 |
|------|------|
| `create_session` | 新建对话 |
| `get_user_session` | 校验会话存在且属于当前用户 |
| `save_message` | 存一条消息，citations 转 JSON 存库 |

**`citations` 存库：**

```python
citations=[c.model_dump() for c in citations]
# → [{"document_id":1, "chunk_id":2, "title":"...", "snippet":"..."}]
```

#### 5.3 `ask_in_session` — 非流式一问一答

```66:83:d:\code\python\enterprise-knowledge-hub\app\services\chat_service.py
async def ask_in_session(db, session, question):
    user_msg = await save_message(..., "user", question)
    if session.title == "新对话":
        session.title = question[:50]
    answer, chunks = run_rag(question, session.user_id)
    citations = chunks_to_citations(chunks)
    assistant_msg = await save_message(..., "assistant", answer, citations)
    return user_msg, assistant_msg, citations
```

**完整流程：**

```
1. 保存用户问题
2. 首条消息 → 会话标题改为问题前 50 字
3. run_rag → LangGraph 检索 + 生成
4. chunks → citations
5. 保存 AI 回答（带 citations）
6. 返回两条消息 + 引用列表
```

#### 5.4 `stream_answer` — 流式输出

```86:117:d:\code\python\enterprise-knowledge-hub\app\services\chat_service.py
async def stream_answer(question, owner_id):
    chunks = retrieve_chunks(...)
    # 拼 context，调 LLM streaming=True
    async for chunk in llm.astream(messages):
        yield json.dumps({"type": "token", "content": chunk.content})
    yield json.dumps({"type": "done", "citations": citations})
```

| 和非流式的区别 | ask_in_session | stream_answer |
|----------------|----------------|---------------|
| LLM 调用 | `invoke`（一次返回） | `astream`（逐 token） |
| 走 LangGraph | 是 | 否（直接检索 + 流式 LLM） |
| 输出 | 完整 answer | 多次 yield JSON |

**为什么流式不走 LangGraph？**  
LangGraph 的 `invoke` 是等全部完成；流式需要边生成边 `yield`，所以在 `stream_answer` 里直接检索 + `astream`，逻辑与 `generate_node` 相同。

**SSE 数据格式：**

```
{"type": "token", "content": "根据"}     ← 每个字/词
{"type": "token", "content": "员工手册"}
{"type": "done", "citations": [...]}     ← 结束 + 引用
```

---

### 6. `api/v1/chat.py` — HTTP 接口

#### 6.1 `_llm_configured` — 前置检查

```32:33:d:\code\python\enterprise-knowledge-hub\app\api\v1\chat.py
def _llm_configured() -> bool:
    return bool(settings.openai_api_key and settings.openai_api_key.strip())
```

没配 API Key 返回 503，避免调用到一半才报错。

#### 6.2 五个接口

| 接口 | 作用 | 关键点 |
|------|------|--------|
| `POST /sessions` | 创建会话 | 默认 title「新对话」 |
| `GET /sessions` | 会话列表 | 按时间倒序，只查自己的 |
| `GET /sessions/{id}/messages` | 历史消息 | 先校验 session 归属 |
| `POST /sessions/{id}/messages` | 非流式提问 | 调 `ask_in_session` |
| `POST /sessions/{id}/messages/stream` | 流式提问 | SSE |

#### 6.3 流式接口细节

```117:138:d:\code\python\enterprise-knowledge-hub\app\api\v1\chat.py
    await save_message(db, session.id, "user", data.question)  # 先存用户消息
    ...
    async def event_generator():
        full_answer = []
        async for line in stream_answer(...):
            # 收集 token，转发给前端
            yield f"data: {line}\n\n"   # SSE 格式
        # 流结束后拼完整回答，存 assistant 消息
        await save_message(db, session.id, "assistant", answer_text, citations)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**时序：**

```
1. 校验 session
2. 立即保存 user 消息（流开始前）
3. 开始 SSE 流
4. 每个 token → yield 给前端
5. 流结束 → 拼完整 answer → 保存 assistant 消息
```

**为什么 user 消息先存、assistant 后存？**  
用户一提问就要进历史；AI 回答要等流式结束才有完整文本。

**SSE 格式 `data: {...}\n\n`：** 浏览器/EventSource 标准，前端可逐行解析。

---

## 五、一次完整问答的数据流

以「年假有几天？」为例：

```
① POST /chat/sessions
   → 创建 session id=1, title="新对话"

② POST /chat/sessions/1/messages
   body: {"question": "年假有几天？"}

③ get_current_user → user.id = 1

④ ask_in_session:
   a. INSERT qa_messages (role=user, content="年假有几天？")
   b. session.title → "年假有几天？"
   c. run_rag("年假有几天？", owner_id=1)
      ├─ retrieve_node: ES 搜到 2 个 chunk
      └─ generate_node: LLM → "根据员工手册，年假为 10 天"
   d. chunks → citations
   e. INSERT qa_messages (role=assistant, content=..., citations=[...])

⑤ 返回 ChatAnswerResponse:
   {
     "answer": "根据员工手册，年假为 10 天",
     "citations": [{"title": "员工手册", "snippet": "年假 10 天..."}],
     "user_message": {...},
     "assistant_message": {...}
   }
```

---

## 六、非流式 vs 流式对比

```
非流式 POST /messages
  ask_in_session
    → run_rag (LangGraph)
      → retrieve → generate (invoke)
    → 一次返回完整 JSON

流式 POST /messages/stream
  save user message
  → stream_answer
    → retrieve_chunks（直接调 ES，不走 Graph）
    → llm.astream（逐 token yield）
  → 流结束 save assistant message
  → SSE 持续推送
```

| | 非流式 | 流式 |
|--|--------|------|
| 用户体验 | 等几秒后一次显示 | 打字机效果 |
| 实现 | LangGraph 完整流程 | 检索 + 直接 astream |
| 历史保存 | ask_in_session 内完成 | generator 结束后保存 |
| 适用 | API 调用、测试 | 前端 Chat UI |

---

## 七、关键概念小结

| 概念 | 在项目中的体现 |
|------|----------------|
| RAG | retrieve_chunks + LLM generate |
| LangGraph | `rag_graph.py` 两节点工作流 |
| State | `RAGState` 在节点间传递 |
| Prompt 工程 | System Prompt 约束不编造 |
| 引用溯源 | chunks → citations → 返回前端 |
| 会话管理 | qa_sessions + qa_messages |
| SSE 流式 | StreamingResponse + event_generator |
| 权限隔离 | owner_id 过滤 ES + session 归属校验 |

---

## 八、和简历技术栈的对应

| 简历技术 | 项目中的体现 |
|----------|-------------|
| LangChain | ChatOpenAI、SystemMessage、HumanMessage |
| LangGraph | retrieve → generate 工作流 |
| ElasticSearch | retrieve_chunks 检索 |
| RAG | 检索 + Prompt 增强 + LLM 生成 |
| 引用溯源 | citations JSON |

阶段 6 可在此基础上加：向量检索、重排序、Mem0 记忆、LangFuse 监控、多步 Agent 等。

---

如果你想继续深入，可以选一个方向我单独展开：

1. **LangGraph 原理** — State、Node、Edge 怎么协作  
2. **Prompt 设计** — 如何减少幻觉、提高准确率  
3. **流式 SSE** — 前后端怎么对接  
4. **阶段 6** — 权限、统计、异步任务怎么接