**结合front-canvas,帮我讲一下agent-server-main这个项目解决了什么问题，通俗点讲，我怎么给面试官讲。**
可以，你可以把它讲成一句很通俗的话：
frontend-canvas 是营销平台的操作界面，用户在上面配置 Journey、编辑模板、和 Emma 对话；agent-server-main 就是背后的 AI 大脑，负责把用户的话变成可执行的 Agent、SQL 查询、流程图、模板内容和结构化结果。
面试时可以这样讲：
“这个项目解决的核心问题是：营销自动化平台里有很多复杂操作，比如圈选客群、分析用户行为、生成营销流程、生成邮件/SMS/Push 模板。如果完全让运营手动做，门槛比较高；但如果前端直接接大模型，又会有几个问题：模型不知道业务数据结构、不会安全地查数据、输出格式不稳定，也没法直接变成前端画布能渲染的 Journey 或模板。
所以我们做了 agent-server-main，把 AI 能力沉到一个  独立服务里。前端 frontend-canvas 负责用户交互，比如 Emma 聊天窗口、Journey 画布、Agent 节点配置；后端 agent-server-main 负责模型接入、Prompt 管理、Tool 调用、Text-to-SQL、结构化输出和运行日志。这样用户在前端说一句需求，后端可以调用对应工具查数据、生成结构化结果，再返回给前端渲染成客群列表、流程图、模板预览或洞察结果。”
可以再具体一点：
“举个例子，运营想做一个营销活动：找出最近有互动但没转化的用户，然后生成一条 Journey 和对应邮件模板。前端 Emma 收到用户输入后，会请求 agent-server-main 的 Emma 接口。后端不是简单把问题丢给模型，而是给模型配置了一组业务 Tool，比如查询用户数据、生成 audience、输出 journey、输出 template。模型调用这些 Tool 后，返回的是前端能消费的结构化数据。比如 Journey 会按 nodes、edges、conditions 的结构返回，前端就可以把它渲染到 ReactFlow 画布里。”
你可以强调你做的价值：
“我参与的重点是 AI 能力和前端业务场景之间的连接。前端这边要处理流式对话、工具调用结果渲染、流程图和模板的容错展示；后端这边要让 Agent 能根据配置加载模型、Prompt、Tool 和输出 Schema，并且支持调试、缓存和日志。通俗讲，就是把‘大模型聊天’变成了一个能真正操作营销系统的 AI 助手。”
几个代码对应点你可以看：
- Emma 前端调用： [src/models/emma.tsx](D:\\code\\rengage\\frontend-canvas\\src\\models\\emma.tsx)
- Emma 后端工具链： [src/routes/api/ai-model/emma/index.ts](D:\\code\\rengage\\agent-server-main\\agent-server-main\\src\\routes\\api\\ai-model\\emma\\index.ts)
- Journey 里选择 Agent 节点： [agentConfigPanel.tsx](D:\\code\\rengage\\frontend-canvas\\src\\pages\\workflowPage\\canvas\\nodeDetailPanel\\agentConfigPanel\\agentConfigPanel.tsx)
- Agent 配置变实例： [src/plugins/agents.ts](D:\\code\\rengage\\agent-server-main\\agent-server-main\\src\\plugins\\agents.ts)
- Agent 调试流式输出： [src/routes/api/agent/index.ts](D:\\code\\rengage\\agent-server-main\\agent-server-main\\src\\routes\\api\\agent\\index.ts)
面试里最稳的一句话是：
“这个项目不是单纯做聊天机器人，而是把 AI 接入到营销自动化业务流程里，让模型可以通过 Tool 查询业务数据、生成结构化营销资产，并且让前端画布可以稳定消费这些结果。”

**你讲一下 agent-server-main 这个项目里，一个 Agent 是怎么从“配置”变成“可运行实例”的？**
请按链路回答：
- Agent 配置存在哪里
- 里面包含哪些关键字段
- 后端运行时怎么读取配置
- 怎么创建 LLM
- 怎么创建 Tool
- 最后怎么用 createReactAgent 组装成可运行 Agent

Agent 配置主要存 MySQL，通过 Prisma 管理，核心表有 agent、agent_setting、agent_model、agent_datasource。  
agent 表里保存 Agent 基本信息和 config，config 里主要包括 prompt、actions、input、responseFormat 等；agent_setting 存 Agent 级或租户级运行参数，比如 model、temperature、timeout；agent_model 存模型厂商、模型名、API Key、Base URL；agent_datasource 存外部数据源配置。  
运行时后端调用 getAgent(uuid)，如果内存缓存里有就直接复用；没有就查数据库读取 Agent 配置和运行设置。然后通过 createLLM 根据模型配置创建具体 LLM，比如 OpenAI、Anthropic、DeepSeek、Google 或 custom OpenAI compatible。  
Tool 部分会遍历 actions 和 input，调用 createTool 动态创建 LangChain Tool，比如时间工具、ClickHouse 查询工具、Snowflake / Databricks 数据源工具。  
最后用 LangGraph 的 createReactAgent 把 llm、tools、prompt 和 responseFormat 组装成一个可运行 Agent。正式运行时调用 agent.invoke，调试时调用 agent.stream 输出节点事件。

**那为什么这个项目里要做 Agent 缓存？**
**缓存的是最终 Agent 对象，还是构建中的 Promise？这样设计有什么好处和风险？**
*为什么要缓存 Agent？*
因为每次构建 Agent 都挺重，不只是 new Agent：
- 要查 agent 配置
- 要查 agent_setting
- 要查 agent_model
- 要创建 LLM 实例
- 要遍历 actions/input 创建多个 Tool
- SQL 类 Tool 还可能要 DESCRIBE TABLE 拉表结构
- 外部数据源 Tool 还可能要创建 Snowflake / Databricks 连接
如果每次运行都重新构建，首包慢、接口耗时高，而且并发请求会重复打数据库和外部数据源。
*为什么缓存 Promise？*
它缓存的是构建中的 Promise，而不是等 Agent 构建完成后才缓存结果。好处是可以合并并发首次请求。  
比如同一个 Agent 同时来了 5 个请求，如果不缓存 Promise，5 个请求都会各自查库、初始化 Tool、创建连接。缓存 Promise 后，第一个请求开始构建时就把 Promise 放进缓存，后面 4 个请求直接 await 同一个 Promise，最终只构建一次。
*风险是什么？*
主要有 4 个：
1. 失败 Promise 被缓存
   如果第一次构建失败，缓存里可能留下失败 Promise，后续请求一直失败。
   解决：catch 里清除缓存。
2. 配置变更后缓存过期
   Agent、模型、数据源、setting 变更后，旧 Agent 不能继续用。
   解决：更新配置时调用 clearAgent(uuid)，租户级设置变化时批量清理相关 Agent。
3. 单机内存缓存不适合多实例部署
   多 pod / 多实例下，每个进程各有缓存，更新通知不一致。
   解决：用 Redis pub/sub 或版本号机制做分布式失效。
4. 长时间不清理会占内存
   Agent 太多时内存会涨。
   解决：加 LRU / TTL。
*面试一句话*
Agent 构建比较重，所以用了内存缓存。这里缓存的是 createAgent(uuid) 返回的 Promise，好处是并发首次请求可以合并成一次构建，避免重复查库和初始化 Tool。
风险是失败 Promise、配置过期、多实例缓存不一致和内存增长。对应可以在构建失败时删除缓存，配置更新时主动 clear，分布式部署时用 Redis pub/sub 做失效通知，再加 TTL 或 LRU 控制内存。

**那 agent-server-main 里 Tool 是怎么创建的？**
**比如用户配置了一个 ClickHouse 查询工具，后端怎么把它变成 Agent 可以调用的 Tool？**
*我的回答，比较直白*
通过getAgent(uuid)，从DB读出config，根据config中type，选择对应的执行函数，并将执行函数，name,description组装成tool，然后通过createReactAgent 去调用
*ai的回答*
Tool 是在构建 Agent 的时候动态创建的。getAgent(uuid) 会读取 Agent 的 config.actions 和 config.input，遍历启用的 action，根据每个 action 的 type 调用 createTool。  
createTool 里面会根据类型走不同分支，比如 getCurrentTime、userProfile、userEngagement、queryDB、dataSource。每个分支最后都会用 LangChain 的 tool() 包装成标准 Tool，包含 name、description、schema 和真正的执行函数。  
以 ClickHouse 的 queryDB 为例，后端会先创建当前租户对应的只读 ClickHouse client，然后并发执行 DESCRIBE TABLE 获取用户画像、行为事件、邮件、短信、Push、In-App 等表结构。接着把字段名、字段类型和一些业务语义写进 Zod schema 的 description 里。  
Agent 运行时，模型看到 Tool 的 description 和 schema，就会生成符合参数结构的调用，比如 { sql: "..." }。Tool 收到 SQL 后执行查询，把结果转成 JSON 返回给模型，模型再基于查询结果生成结构化输出
这样做的价值是把数据库查询能力变成模型可调用工具，并且通过真实表结构降低 Text-to-SQL 字段幻觉。

**/api/agent/test 里为什么要用 reply.hijack()？**
**如果不用它，普通 Fastify 返回有什么问题？**
在 Fastify 里，正常接口一般是：
return reply.send(data)
也就是后端处理完，再一次性返回结果。
但 /api/agent/test 不一样，它要边运行边推送事件，比如：
- 用户输入
- 模型响应
- 工具调用
- 工具返回
- 最终结构化输出
所以它不能等全部结束再返回，而是要直接操作底层 response stream。
reply.hijack() 的作用就是：
告诉 Fastify：这个响应我自己接管了，你不要再自动帮我序列化和 reply.send()，我会自己用 reply.raw.write() 一段一段往前端写数据。

面试可以这样说：
/api/agent/test 需要 SSE 流式输出 LangGraph 的节点事件。如果用普通 reply.send()，只能在 Agent 完成后一次性返回，前端看不到中间过程。  
所以这里用 reply.hijack() 接管底层响应流，设置 Content-Type: text/event-stream，然后在 Agent stream 过程中不断调用 reply.raw.write() 写入 event 和 data。等 Agent 结束后，再写 done 并 reply.raw.end()。

为什么不用普通返回？
普通返回适合一次性 JSON 响应，不适合长连接流式事件。SSE 需要服务端保持连接，并持续写入多段事件。

你记这个就行：
reply.hijack() = 我自己接管 response，用于 SSE 这种持续写数据的场景。

**你讲一下 /api/agent/test 和 /api/agent/run 两个接口的区别。**
**它们分别适合什么场景？实现上有什么差异？**
/test 更像预览和调试，不只是看最终答案，而是看模型有没有调用工具、工具返回什么、结构化输出是否符合预期。
/api/agent/test 用于 Agent Builder 调试，前端传临时配置，后端临时构建 Agent，通过 SSE 返回 LangGraph 节点事件；/api/agent/run 用于正式执行，根据 uuid 获取缓存 Agent，调用 invoke 返回结构化结果，并记录 token、耗时和成功失败日志。

**这个项目里用了 responseFormat。**
**它在 Agent 里起什么作用？为什么要让用户配置输出 Schema？**
responseFormat 本质上是一个 JSON Schema，用来约束 Agent 最终输出的结构。后端在创建 createReactAgent 时会把它传进去，这样 Agent 在工具调用和推理结束后，会进入结构化输出阶段，生成符合 Schema 的 structuredResponse。  
之所以让用户配置输出 Schema，是因为 Agent 会被挂载到不同业务流程节点里，不同节点需要的返回结构不一样。比如有的节点只要 flag，有的要用户分组列表，有的要营销文案，有的要推荐内容。用 Schema 固定输出，可以让下游系统稳定消费，而不是解析一段自然语言。  
前端还支持根据 Prompt 自动生成 Schema，降低运营配置成本。

**如果 Agent 最终没有按 responseFormat 输出合法 JSON，或者字段缺失，你会怎么处理？从后端和前端两个角度说说。**
后端会先对 responseFormat 本身做校验，确保它是合法 JSON Schema，避免保存非法配置。Agent 执行完成后，再用 AJV 校验 structuredResponse 是否符合 Schema。  
如果字段缺失或类型不对，可以做一次 retry，把校验错误、原始输出和 Schema 一起交给模型，让它按 Schema 修复。重试后仍失败，就返回结构化错误，并记录日志，方便后续排查 Prompt 或 Schema 设计问题。  
前端侧也会做一层校验和兜底展示，比如 Schema 编辑时校验 JSON 格式，运行结果不合法时提示用户，而不是直接让页面渲染失败。
生产链路里不能依赖前端兜底，最终还是以后端校验为准，因为下游系统消费的是后端返回的结构化结果。

**agent-server-main在前端emma聊天机器人起到了啥作用**
agent-server-main 在前端 Emma 聊天机器人里，作用可以理解成：Emma 的后端大脑和工具执行层。
前端的 frontend-canvas 主要负责聊天界面、输入框、消息流式展示、工具调用结果渲染；真正决定 Emma 怎么理解问题、用哪个模型、能调用哪些业务能力、返回什么结构化结果，是 agent-server-main 做的。
面试时可以这样讲：
“前端 Emma 不是直接调大模型，而是请求 agent-server-main 的 /api/ai-model/emma 接口。这个服务会先根据租户和功能场景选择对应模型，然后加载 Emma 的 Prompt 配置，把用户历史消息、品牌上下文、业务数据一起组装成模型输入。执行过程中，后端会给模型挂载一批业务 Tool，比如查询用户数据、生成客群、生成 Journey、生成模板、查询活动效果等。模型不是只返回一段聊天文本，而是可以通过 Tool 返回结构化结果，前端再把这些结果渲染成客群卡片、流程图、模板预览或洞察内容。”

**前端Agent模块到底是做啥的**
“前端 Agent 模块主要是一个配置化 AI Agent 的管理后台。它让运营可以配置 Prompt、模型、输入、Tool 和输出 Schema，并且支持在线测试。配置好的 Agent 可以挂到 Journey 流程节点里，在营销流程运行时由后端 agent-server-main 执行，返回结构化结果参与后续决策。”

**langgraph如何做agent编排的**
假设 Agent 配置为：

Prompt：「根据 @userId 查用户画像，生成个性化邮件，输出 @contentBlock」
Actions：userProfile（ClickHouse Tool）
responseFormat：{ contentBlock: string }
LangGraph 内部大致会：

1. [agent]     读 Prompt + input，决定先查 userProfile
2. [tools]     执行 ClickHouse SQL，返回用户数据 JSON
3. [agent]     根据数据生成邮件内容
4. [generate_structured_response]  输出 { "contentBlock": "..." }
5. 返回 structuredResponse 给 /api/agent/run
若一步不够（例如先查画像再查行为），会在 agent ↔ tools 之间多轮循环，直到模型认为可以生成最终结果。



1. 参与 Agent 配置化执行引擎建设，将前端配置的 Prompt、输入数据源、Actions、模型参数和 responseFormat 动态转换为 LangGraph createReactAgent 实例，实现低代码方式创建和运行 AI Agent。
2. 封装多模型接入层，支持 OpenAI、Anthropic、DeepSeek、Google Gemini 以及自定义 OpenAI Compatible API，按租户和业务场景选择不同模型，方便后续模型切换和成本优化。
设计 Agent 工具体系，将用户画像、用户行为、FeedManager、ClickHouse 查询、Snowflake、Databricks 等能力封装为 LangChain Tool，让模型可以根据任务自动调用外部数据源完成推理和生成。
3. 实现 Agent 流式测试链路，基于 Fastify reply.hijack() 和 SSE 推送 LangGraph 执行过程，将用户输入、模型响应、工具调用、工具返回和结构化结果实时展示给前端，提升 Agent 调试体验。
4. 实现 Agent 实例缓存机制，按 Agent UUID 缓存已构建的模型和工具实例，避免每次请求重复加载配置、初始化模型和创建工具；在 Agent 配置、模型、数据源或设置更新后主动清理缓存，保证配置变更生效。
5. 实现 Agent 正式运行链路，支持工作流节点调用 /api/agent/run 执行指定 Agent，并记录执行耗时、输入输出 Token、结构化结果、成功失败状态等日志，为后续监控和效果分析提供数据基础。
6. 建设 Agent 指标统计能力，基于 agent_log 聚合运行次数、平均响应时间、成功数、失败数等指标，并在前端工作流节点详情中展示模型、温度、成功率和耗时变化。
7. 实现 Prompt 和输出 Schema 辅助生成能力，基于 LLM 自动优化 Agent Prompt，并根据 Prompt 推断 JSON Schema，使 Agent 输出从自然语言变为可被业务系统消费的结构化结果。
为 Emma AI 助手提供后端 AI 能力支持，基于 Vercel AI SDK streamText 实现流式对话，封装受众分析、SQL 查询、Journey 查询、模板生成、Moment 生成等业务工具，支撑前端聊天式创建营销资产。
8. 支持多租户隔离，通过请求头中的 tenant-uuid、user-uuid 区分租户和用户，按租户管理 Agent、模型 Key、数据源、默认设置和执行记录。


**我理解的流程**
分为/api/agent和/api/ai-model两块
`/api/agent`: 可配置的Agent编排和运行平台
*作用（解决什么问题）*
在 Rengage 里，运营/产品往往需要「根据用户画像、触达日志、外部数仓等，生成一段个性化结果」（文案、决策、结构化字段等）。

/api/agent 的价值是：
   不用写代码就能搭 Agent（prompt + 工具 + 输出 Schema）
   挂进工作流节点正式跑（/run），并记日志、看指标
   多租户隔离（tenant-uuid），模型和数据源按租户配
*做了什么（功能面）*
Agent CRUD:创建/改/查/删、分页、文件夹分类
Setting / Model:Agent 级 or 租户级：模型、温度、超时；agent_model 管多厂商密钥/模型
Data Source:外部数仓（Snowflake / Databricks 等）配置与连通性探测
Test（SSE）:调试：实时推送思考、tool 调用、结构化结果
Run:正式执行：返回 structuredResponse，可选写 agent_log
辅助:/output-schema、/generate-prompt 用 LLM 帮生成 Schema / 优化 Prompt
Metrics:按节点/时间窗汇总成功失败、耗时、token
In-App 模板:另有一条用 LLM 生成带占位符的 In-App HTML

*怎么做的（运行机制）*
1. 配置落库
agent 表存配置；agent_setting 决定用哪个模型/温度（Agent 自定义 → 租户默认 → 租户最新 agent_model）。

2. 构建 Agent（plugins/agents.ts）
getAgent(uuid)：

读 DB 配置 + setting
createLLM 建模型
createTool 按 actions / input 挂工具
createReactAgent（LangGraph）组装：llm + tools + prompt + responseFormat
进程内缓存；更新 Agent 时 clearAgent 清缓存

*createReactAgent（LangGraph）的作用*
createReactAgent 来自 @langchain/langgraph/prebuilt，内部是一个 State Graph（状态图），实现经典 ReAct 循环

用户 input（messages）
        ↓
   [agent / LLM]  ← 看历史 + prompt，决定下一步
        ↓
   要调工具？ ──是──→ [tools] 执行 SQL/API → 结果写回 messages
        ↑                    │
        └────── 继续推理 ─────┘
        │
       否（信息够了）
        ↓
   [generate_structured_response] 按 responseFormat 吐结构化 JSON
        ↓
   structuredResponse

所以 LangGraph 在这里干的事是：

维护对话/工具调用状态（messages 一路累积）
控制循环：模型要 tool 就执行，再喂回模型，直到结束
按 Schema 收口：最后走 structuredResponse，而不是一段自由文本


3. 工具从哪来（plugins/llm.ts → createTool）

userProfile / userEngagement / queryDB:ClickHouse：画像、事件、邮件/Push/SMS/InApp 日志
feedManager:调 FeedManager 拉未发送 feeds
dataSource:Snowflake / Databricks 等外部数仓查询
getCurrentTime:当前时间

`/api/ai-model`:面向产品功能的AI能力后台
是产品侧固定 AI 能力的后台：给 Emma、Content Hub、Moments 等直接调模型，不是给用户自己配置 Agent 的。
*作用（解决什么问题）*
产品功能需要「对话流式输出、生图、改文案、起标题」等，但：

   Prompt 由运营在 Template/Emma Config 里配
   模型密钥按租户在 ai_model 里配
   业务数据要打 Presentation Layer / 模板服务 / 抓网页等

*做了什么（功能面）*
1. 模型管理（/api/ai-model）：与agent模块无关，在前端页Settings → AI Model Keys里可以配置模型
租户级 CRUD：provider / model / api_key / features。创建/更新时会用 LangGraph 探针测一下能不能调通。

2. Emma 相关
emma聊天具体流程:
前端发 messages + teamUuid + userUuid
        ↓
createAiModel(Emma)          ← 租户在 ai_model 里配的模型
        ↓
拉 allInOne 的 Emma Config    ← Template 服务最新 prompt
        ↓
拼 messages：
  system(渲染后的 prompt) + 最近 50 条对话
        ↓
streamText（最多 10 步）
  模型可边说边调 tools：
  受众 / SQL / Journey / Moment / 模板 / 搜 Journey …
        ↓
createDataStream 流式返回前端（带 message uuid）

3. Content Hub / 其它
支撑 Content Hub 前端的「AI 写文案 / 填表 / 出图改图」，让运营在内容创作里直接调 AI，而不走可配置 Agent 那套。
比如在邮件编辑的时候直接让ai改图


*怎么做的（运行机制）*
createAiModel是根据租户（也就是公司）的id去数据库里取对应的模型

请求（messages + teamUuid …）
  → createAiModel(对应 EFeature)
  → 拉 Emma/Template prompt
  → streamText / generateObject
       ├─ 无 tool：直接流式文本（editor）
       ├─ 有 tool：多步调用 Presentation Layer / 模板 / WebFetch（emma、assistant）
       └─ 生图：DALL·E → uploadToS3
  → Data Stream / JSON 返回前端

