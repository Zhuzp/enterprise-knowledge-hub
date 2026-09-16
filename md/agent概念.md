**llm是什么**
  -LLM：*用 Transformer 当骨架，喂海量文本训练出来、能理解和生成语言的大模型。*
  每次输出，其实都在做同一件事：给定前面的字，预测下一个字（token）最可能是什么。
  预测亿万次之后，模型间接学到了：语法（主谓宾怎么搭）、常识（水在 100°C 沸腾）、写作风格、代码格式、推理套路……
  所以 LLM 的「智能」不是规则写进去的，是从海量文本里统计/压缩出来的规律。
  训练分以下几步：
  预训练（Pre-training）-> SFT（监督微调）->RLHF

**Transformer是什么**
  - Transformer：*底层骨架*（模型的结构）
  Transformer 是一种神经网络结构，专门用来处理「一串词之间的关系」。
  以前模型读句子，往往从左到右一个词一个词记（RNN）。Transformer 换了个思路：句子里每个词，都可以直接「看见」其他所有词，再判断谁和谁更相关。
  核心机制：自注意力机制（Self-Attention）、 并行计算

**RAG是什么？**
  Retrieval-Augmented Generation（检索增强生成）。
  RAG：*给 LLM 外挂专属知识库*
  RAG = 先查资料，再让 LLM 根据查到的内容回答。
  为什么需要 RAG？
  LLM 有两个硬伤：
    不知道你的私有知识（公司内部制度、自家产品文档、最新工单）
    容易瞎编（训练里没记牢的，也会编得像真的——幻觉）
    RAG 的解法很直白：别让它硬猜，先帮它把相关段落找出来，塞到 prompt 里，再让它答。
  

**什么是 AI Agent？和传统 Chatbot、RAG 有什么区别？**
Agent = 会自己决定「下一步干什么」的 LLM 应用，不只是一问一答。
普通 ChatBot 的流程：
    用户问 → LLM 想一遍 → 直接输出答案 → 结束
RAG：
    先检索文档，再一次性生成
Agent 的流程：
    用户问 → LLM 想：我需要查资料吗？要调工具吗？
      → 执行动作（查库 / 调 API / 跑 SQL）
      → 看结果 → 再想：够了吗？还要再查吗？
      → 输出最终答案 → 结束
LLM本身只会生成文字。Agent在外面包了一层行动循环，就是ReAct，下面问题讲

**ReAct 是什么？执行流程是怎样的？**
  - ReAct = 让 LLM 交替做两件事——先想（Reason），再做（Act），再看结果，再想下一步。
  全称 Reasoning + Acting（推理 + 行动）。
  循环：
    ┌─────────────────────────────────────┐
    │  感知：收到用户问题 + 上一步结果      │
    │    ↓                                │
    │  推理：Thought（我该怎么做？）        │
    │    ↓                                │
    │  行动：Action（调某个 Tool）         │
    │    ↓                                │
    │  观察：Observation（Tool 返回什么）   │
    │    ↓                                │
    │  再推理……直到任务完成或达到步数上限   │
    └─────────────────────────────────────┘
  - 为什么需要ReAct
    普通 LLM 对话是一次性输出：用户问 → 模型直接答 → 结束
    很多问题这样搞不定，比如：
    需要查数据库才能答、需要分好几步（先查规则，再查数据，再判断）、中间结果会影响下一步怎么做
    ReAct 的做法：别一次性猜答案，改成「想一步、做一步、看一步」的循环。

**Function Calling 完整流程是什么？**
  - 你告诉模型「有哪些函数、参数长什么样」，模型决定要不要调、调哪个、传什么参数，你的代码执行完把结果还回去，模型再据此生成最终回答。
    定义 Tool Schema -> 请求时传入tools -> 模型返回tool_calls -> 服务端执行函数 -> 以tool message回注结果 -> 模型生成最终回答；模型只负责"决定调什么"，执行在应用侧，多轮tool_calls构成ReAct循环。
  - Tool schema是写给 LLM 看的「函数说明书」——告诉模型这个工具叫什么、干什么、需要什么参数。其中：
    name: 工具唯一标识，模型在tool_calls里引用
    description: 模型靠它判断"什么时候该用这个工具"
    parameters: 参数名、类型、是否必填、取值范围
  - tool_calls: 模型发给你的一张"工单"。
    tool_calls = 模型说"请你去执行这些函数，执行完把结果告诉我"
  - 所以拿到llm返回的tool_calls之后，我要手动遍历tool_calls去执行里面的函数
  - 拿到函数结果后用role:tool消息把结果还给llm，具体操作：
    我执行完，往messages数组里append一条tool消息,然后再次调用chatAPI
    {
        "role": "tool", //固定 "tool"
        "tool_call_id": "call_abc123", // 必须和 tool_calls 里的 id 完全一致
        "content": "{\"count\": 3}" //函数返回值，通常是 JSON 字符串
    }
    
  - 然后llm根据最终的content回答

**Agent 的核心模块有哪些？**
  - LLM（大脑）：理解输入、推理决策、生成文字
    在 Agent 里 LLM 不只「回答问题」，还要：
    - 决定要不要调工具
    - 决定调哪个、参数填什么
    - 读完 tool 结果后决定下一步
    - 判断什么时候可以输出最终答案
  - Tools（手）：让 Agent 能接触外部世界。
    Tools 可以是：
    - 数据查询（SQL、向量检索/RAG）
    - 外部 API（HTTP 调用）
    - 文件操作（读/写/搜索）
    - 系统能力（获取时间、发通知）
  - Memory（记忆）：让 Agent 在多轮交互中不丢上下文。
  - Planning（规划）：复杂任务拆步、决定执行顺序。
    两种模式:ReAct  Plan-and-Execute(这个不知道)
  - Orchestration（编排/循环）：把上面所有模块串成循环，控制何时开始、何时停。
    和ReAct区别：
     ReAct：循环里每一步怎么想，怎么做（每一圈做什么）
     Orchestration：谁来驱动这个循环、怎么停、怎么管状态（整个循环怎么跑、何时停）
    ReAct 是循环的内容，Orchestration 是循环的机器。Orchestration 是包住 ReAct 的外层引擎。ReAct只规定一轮的结构，但不负责：这个循环跑几次，什么时候停，出错怎么办之类的。
  - Output Control（输出控制）：约束 LLM 最终输出的格式和内容。

**什么时候该用 Agent，什么时候不该用？**
    步骤固定、输入输出明确 → 不用 Agent；
    路径不确定、需要调外部系统、要多步决策 → 用 Agent。
    Agent 适合路径不确定、需动态组合多 Tool、需中途纠错的开放任务；不适合步骤固定、低延迟、高确定性、单次 LLM 可完成的场景。判断标准是：流程能否事先写死——能写死用 Chain/RAG/Workflow，写不死才用 Agent。

**微调是什么？**
    微调 = 在已经训练好的大模型基础上，用特定数据再训练一轮，让它更擅长某件事。
    Prompt：不改模型，改输入
    RAG：不改模型，加外部知识
    微调：改模型权重
    什么时候该微调：
        需要固定的输出风格/语气、高频任务的格式总出错、有大量高质量标注数据、要降低 prompt 长度（省 token）、小语种/方言表达
    先试 Prompt → 不够加 RAG → 还不够且数据充足，才考虑微调。
    - 微调是在预训练模型基础上，用特定任务数据（SFT）或人类偏好（RLHF/DPO）继续训练，改变模型权重以适配特定行为/风格/领域；与 RAG（外挂知识）和 Prompt（输入约束）不同，微调改的是模型本身；成本低效方案是 LoRA；选择顺序通常是 Prompt → RAG → 微调。

**Multi-Agent是什么**（还没接触过，先理解概念吧）
  Multi-Agent = 多个 Agent 分工协作，各干各的活，组合完成一个复杂任务。
  每个 Agent 有自己的 角色、Prompt、Tools，只 Focus 自己擅长的事。
  四种常见协作模式：
  1. Supervisor（主管分发）⭐ 最常用
    一个主管 Agent 接收用户请求，决定交给哪个专家 Agent
    - Supervisor → 交给 数据分析 Agent
    - Supervisor → 交给 文案 Agent（带上分析结果）
    - Supervisor → 汇总返回

  2. Pipeline（流水线）
    Agent 按固定顺序传递，像工厂流水线
    Agent A（数据采集）→ Agent B（分析）→ Agent C（生成报告）
    每个 Agent 的输出是下一个的输入。顺序固定，但每步内部可以 ReAct。

  3. Handoff（交接）
    Agent 做一半发现「这不是我的活」，主动交给另一个 Agent

  4. Parallel（并行 + 汇总）
    多个 Agent 同时干活，最后由一个 Agent 汇总：

  *解决了什么问题*
    1. 单 Agent Prompt 太长、Tool 太多
      一个 Agent 塞 20 个 Tool + 5000 字 system prompt → 模型选择准确率暴跌。
      拆成多个 Agent，每个只带 3~5 个 Tool + 短 prompt → 每个 Agent 更专注、更准确。
    2. 角色行为差异大：一个 Agent 很难同时扮演三种截然不同的角色。
    3. 复杂任务需要不同专业能力
    4. 隔离失败范围：一个 Agent 出错不影响其他 Agent。
  什么场景该用
    1. 客服 + 工单 + 退款
    2. 内容生产流水线
    3. 数据分析 + 报告生成
    4. 代码开发
  判断标准：
  如果一个 Agent 的 prompt 还没爆、Tool 选择还准、延迟可接受 → 别拆。
  只有当单 Agent 明显「管不过来」了，才拆成 Multi-Agent。

  - Multi-Agent 的代价
    延迟、成本、调试难、通信开销、过度设计

  *面试一句话*
  Multi-Agent 是多个专责 Agent 协作完成复杂任务的架构，常见模式有 Supervisor 分发、Pipeline 流水线、Handoff 交接和 Parallel 并行；适用于 Tool 过多、角色差异大、任务需多专业能力的场景；代价是延迟、成本和调试复杂度上升，应优先单 Agent，管不过来再拆。

**Embedding（向量化）是什么**
  把文字变成一组数字（向量），意思相近的文字，数字也相近。
  *为什么需要 Embedding*
    计算机不认识「猫」和「猫咪」意思差不多。它只认数字。
    Embedding 的作用就是：把语义变成计算机能比较的数字。
  *怎么理解向量*
    可以把向量想象成语义地图上的坐标：
    意思相近的词，在地图上靠得近。Embedding 模型就是把文字映射到这个地图上的坐标。
  *面试一句话*
    Embedding 是用 Embedding 模型将文本映射为固定维度的稠密向量，语义相近的文本向量距离近；在 RAG 中用于语义检索——建库时对 chunk 向量化存储，查询时对问题向量化并在向量库中找最近邻；需与 BM25 混合以互补字面匹配能力。

**Token / Context Window**
  *Token：Token 是 LLM 处理文字的最小单位——模型不是按「字」或「词」读写，而是按 Token。*
    英文：1token≈0.75单词
    汉字：1token≈0.5汉字
    代码/符号：变化大
    
    LLM 的一切计量都按 Token：
      输入长度
      输出长度
      API费用:输入 token × 单价 + 输出 token × 单价
      延迟:token 越多，生成越慢

  *Context Window：Context Window = 模型一次性能读写的 Token 总量上限。*
    不是「输入可以 128K」——输入 + 输出共享这个预算。
  *面试一句话*
    Token 是 LLM 处理文字的最小单位，Context Window 是模型一次请求的 Token 总量上限（输入+输出共享）；在 Agent 中 Context 压力更大，因为 ReAct 每轮都追加 messages、Tool Schema 占固定开销、Tool 返回结果可能很大；需通过 topK 控制、Tool 结果截断、Memory 压缩和滑动窗口来管理 Token 预算。

**Prompt Engineering 是什么**
  Prompt Engineering = 通过设计和优化输入文字，让 LLM 输出更符合预期的回答——不改模型，只改「怎么说」。
  Prompt 是你和 LLM 之间唯一的沟通界面——模型不会读心，你写什么样的 prompt，它就按什么样的方式回答。
  *常用技巧*
  1. 角色设定（Role Prompting）
  2. 约束与边界
  3. Few-shot（给示例）
  4. Chain-of-Thought（CoT，链式思考）：不让大模型直接输出答案，要求模型输出中间思考步骤，再给出最终答案。
  5. 输出格式约束
  6. 变量占位（Dynamic Prompt）

  *面试一句话*
  Prompt Engineering 是通过设计 system prompt、Few-shot 示例、CoT、输出格式约束和 Tool Schema 描述等手段，在不改模型的前提下控制 LLM 输出行为；在 Agent 中 Prompt 贯穿 system 指令、Tool 说明、RAG 上下文和输出格式；是成本最低、见效最快的 LLM 调优手段，通常与 RAG 和 Tool 约束组合使用。

**Hallucination（幻觉）是什么**
  Hallucination = LLM 生成了看起来合理、语气自信，但事实是错的内容。
  *面试一句话*
  Hallucination 是 LLM 生成看似合理但事实错误的内容，根源是 next-token 预测机制——模型在「猜」而非「查」；缓解需多层防御：RAG 提供依据、Prompt 要求拒答、Tool 调用替代猜测、Structured Output 约束格式、后处理校验；Agent 中幻觉来源分检索层、Tool 解读层和生成层，需 Tracing 定位。

**Hybrid Search（混合检索）是什么**
  Hybrid Search = 同时用多种检索方式找文档，再把结果合并，各取所长。
  单用一种检索总有盲区
  目前一般是
  1. 向量检索：语义相近
  2. BM25检索（关键词检索）：BM25是经典稀疏关键词检索打分算法，一个词越稀有，IDF值越高（逆文档频率），在BM25打分权重越大。与向量检索天然互补。
  3. 图谱检索：
  *混合检索怎么做*
  1. 多路并行召回：每路独立跑，互不影响，各自取 topK 条
  2. 去重：三路结果可能有重叠（同一段文档被多路命中），按 chunk id 去重，但保留「被几路命中」的信息——多路命中通常是高置信信号。
  3. 融合排序:RRF（公式在interview文件里有解释）
  4. 精排 + 截断：RRF 融合结果 → Rerank 精排 → 取 topK 进 LLM
  *rerank*:Cross-encoder 模型对每对 (query, chunk) 打分,按分数重排后的 topK 条（如 10 条）→ 进 LLM
  *rerank相关问题*:
    Bi-encoder 和 Cross-encoder 的区别？
    Bi-encoder 像各自做笔记再比对；Cross-encoder 像两个人面对面讨论是否相关。

  *面试一句话*
  Hybrid Search 是同时使用向量检索（语义）和 BM25（字面）等多种检索方式并行召回，再通过 RRF 按排名融合、Rerank 精排，各补短板以提高召回率；向量擅长同义词和语义关联，BM25 擅长错误码和精确匹配；企业知识库场景几乎都应使用混合检索。


**Chunking 是什么及相关问题**
  Chunking = 把长文档切成适合检索和 Embedding 的小片段，每段单独向量化、单独被检索。
  *为什么必须切：*
    Embedding 模型有输入长度上限（通常 512~8192 token）
    向量把整个 chunk 压成一个向量——太长语义被稀释，「打车费」和段末「HR 共享盘」挤在同一个向量里，检索不准
    LLM Context 有限，检索结果要精炼
  *Chunk Size 怎么定？调大调小牺牲什么？*
    调大：上下文更完整
    调小：语义更聚焦、检索更准
  *Overlap 有什么用？取多少？*
    相邻 chunk 重叠一段，防止边界信息被切断。通常 chunkSize 的 10%~20%。你项目 maxChars/8（约 12.5%）。overlap 必须 < chunkSize，否则死循环。
  *按固定长度切和按语义/结构切有什么区别？*
    固定长度：实现简单，但可能把一句话、一张表格拦腰截断
    按结构切：保留段落/标题/表格完整性，检索质量更高
    最佳实践：结构优先，结构切不开时再按长度 + 边界回溯（句号、换行）

**Structured Output 是什么**
  Structured Output = 强制 LLM 输出符合预定格式的结构化数据（通常是 JSON），而不是自由文本。
  *面试一句话*
  Structured Output 是通过 JSON Schema 约束 LLM 输出为固定结构的 JSON 对象，而非自由文本；在 Agent 场景中用于让下游系统可靠消费 Agent 结果；实现方式包括 responseFormat 参数、Zod Schema 和 OpenAI structured output mode；比 prompt 描述格式更稳定，是 Agent 对接工作流的关键。

**Temperature / Top-p 是什么**
  Temperature 和 Top-p 都是控制 LLM 输出「随机性/创造性」的参数——值越低越确定，值越高越发散。
  *面试一句话*
  Temperature 调整 LLM 输出概率分布的陡峭程度，越低越确定（0≈选最高概率 token），越高越随机；Top-p 通过截断低概率尾部控制候选范围；Agent 中 factual/Tool 选择任务用 0.3，创意生成用 1.0；两者通常只调 Temperature，Top-p 保持默认。

**Memory（记忆）是什么**
  Memory = Agent 记住之前发生过什么的能力——没有 Memory，每轮对话都是全新的，用户说「刚才那个」它完全不知道。
  两层 Memory
  Short-term Memory（短期记忆）：当前会话内的对话历史。
    实现方式：messages 数组，每轮 append user + assistant 消息。
    在 Agent 里就是 LangGraph State 里的 messages 字段——ReAct 每轮的 Thought/Action/Observation 也都存在这里。

  Long-term Memory（长期记忆）：跨会话持久化的信息。
    实现方式：数据库存用户偏好/事实、向量库检索历史相关记忆、定期 summary 压缩
  *面试一句话*
  Agent Memory 分 Short-term（当前会话 messages，含 tool 结果）和 Long-term（跨会话持久化）；核心挑战是 Context Window 有限，通过滑动窗口、LLM 摘要压缩和 Tool 结果裁剪控制 Token 预算；生产实现需考虑加载性能、异步压缩、分布式锁和用户隔离。
  *对话太长 Context 放不下怎么办？*
  优先级：摘要压缩 > 滑动窗口 > Token 截断。
 
 **LangGraph 核心概念** 
  LangGraph = 用「图」来编排 Agent 的执行流程——节点是步骤，边是流转条件，状态在节点间传递。
  *五个核心概念*：
  1. State（状态）：图运行过程中的共享数据容器，每个节点都能读写。
    特点：
      所有节点共享同一个 State
      每个节点返回 State 的更新（不是替换整个 State）
      Agent 里 State 最核心的字段就是 messages
  2. Node（节点）：图中的一个处理步骤，就是一个函数。

  3. Edge（边）：节点之间的连接，定义「做完 A 之后去哪」。
    两种边：
      普通边（固定跳转）
      条件边（Conditional Edge）⭐ 核心：根据 State 的内容决定下一步走哪
    [agent → 有 tool_calls? → tools → agent（循环）
                    → 没有?    → generate → END]

  4. Graph（图）:Node + Edge 组成完整的执行流程。
  5. Checkpoint（检查点）:把 State 持久化到磁盘，支持中断恢复。
    用途：
      Human-in-the-loop：Agent 要调危险 Tool 前暂停，等人工确认
      长时间任务：Agent 跑一半挂了，从 Checkpoint 恢复而不是重来
      多轮会话：跨请求的 State 持久化

**MCP（Model Context Protocol）是什么**
  MCP = 一套标准协议，让 AI 应用（Client）和外部工具/数据源（Server）用统一方式连接——不用每个 Tool 各写一套集成。
  *面试一句话*
    MCP 是 AI 应用与外部 Tool/数据源之间的标准连接协议，采用 Client-Server 架构，支持 Tool 动态发现、Resource 读取和 Prompt 模板；相比硬编码 Function Calling，MCP 实现 Tool 与 Agent 解耦、跨应用复用和独立部署；是 Tool 体系工程化的方向，不是 Function Calling 的替代。

**Prompt Injection 是什么**
  Prompt Injection = 用户通过输入，试图覆盖或绕过 System Prompt 里的规则，让 LLM 做原本不该做的事。
  *面试一句话*
    Prompt Injection 是用户或外部数据通过输入覆盖 System Prompt 规则，诱导 LLM 产生非预期行为的攻击；Agent 场景因可执行 Tool 而风险更大；防御需多层：Prompt 指令分层、输入输出过滤、Tool 权限硬限制（只读/白名单/沙箱）和 Human-in-the-loop，不能依赖 LLM 自觉遵守规则。

**Evaluation（评估）⭐是什么**
  Evaluation = 用可量化的指标和方法，系统性地衡量你的 LLM / RAG / Agent 好不好用、可不可靠。
  *面试一句话*
  Evaluation 是用 Golden Dataset 和量化指标系统性衡量 LLM/RAG/Agent 质量的过程；RAG 评 Recall@K + Faithfulness + Relevance 三联；Agent 额外评 Tool Call Accuracy、Steps、Cost；分离线（上线前 benchmark）和在线（生产监控）；三者独立排查，检索差调检索，生成差调 Prompt，Tool 错调 Schema。

**Streaming / SSE 是什么**
  Streaming = 不等 Agent 全部跑完，边执行边把结果推给前端；SSE 是实现推送的一种 HTTP 协议。

**Agent 缓存是什么**
  Agent 缓存 = 把「配置 → LLM + Tools → 可执行图」的构建结果存起来，同一个 Agent 下次直接用，不用重复构建。
  *面试一句话*
    Agent 缓存将 createAgent 构建结果（LLM + Tools + LangGraph 图）按 uuid 缓存在进程内存中，存 Promise 防并发重复构建；因 Agent 构建成本高（DB 查询 + Tool 初始化 + 图编译）而配置相对静态；配置变更时通过 clearAgent 做 write-through 失效；多实例部署需 Redis 广播或 TTL 兜底；LangGraph 对象不宜序列化，进程内缓存是务实方案。

**RabbitMQ是啥**
RabbitMQ 里面核心角色：**生产者、交换机、队列、消费者**

1. **生产者**：发消息的程序（你的 FastAPI），生产者**不直接把消息发给队列**！
生产者只把消息丢给 **交换机 Exchange**。
2. **交换机 Exchange**：就是一个**消息路由器**。收到消息之后，按照规则把消息分发到不同队列。
3. **队列 Queue**：存放消息的盒子，消息最终存在队列里。消费者从队列拿消息干活。
4. **消费者**：从队列取消息处理（vector_consumer、graph_consumer）。