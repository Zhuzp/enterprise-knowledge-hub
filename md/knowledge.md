**上传到检索**
1.一个文件上传，读取文件内容，判断类型，源文件存MinIO，minio_key写入document数据库 ，上传后投递解析任务，根据文件类型，选择重任务队列/轻任务队列，视频走重任务队列，其他pdf，docx，png,jpg,xlsx走轻队列任务，这边是直连，消息根据routing_key=light/heavy直接投递到对应队列
2.队列接到消息后，开始解析文档，先到document表里查文档记录，修改状态为解析中，从minIO下载原文档二进制，然后调用parse_to_markdown函数进行解析，根据file_type，也就是文件后缀，分发到对应的解析器(PdfParser / DocxParser / ImageParser等)进行解析，解析后的md文档也上传到minIO，将minIO key返回到对象存到数据库里。
文档如何解析？
*pdfParser:逐页文本 + 内嵌图上传 MinIO + OCR（PyMuPDF 逐页抽文本；内嵌图 → MinIO + OCR → 写入 MD）*
    接收PDF bytes（file_data）
    → fitz打开内存流PDF（不落地磁盘）
    → 遍历每一页
        → 更新解析进度回调
        → 提取页面文字，写入Markdown
        → 遍历页面内所有图片
            → 提取图片二进制
            → 上传图片到MinIO，拿到存储key + 访问url
            → OCR识别图片文字
            → 存入assets资源对象（记录图片链接、OCR alt文本、来源页码）
            → Markdown插入图片链接 + OCR注释块
    → 全部页面处理完成，进度回调100%
    → 返回ParseResult（md文本、图片资源数组、metadata）
    
*DocxParser:段落文本 + 内嵌图 + OCR（段落文本；关系里的图片 → MinIO + OCR）*
    接收docx文件bytes
    → BytesIO包装内存流，python-docx打开文档（不落地磁盘）
    → 初始化assets数组、md_parts列表（markdown拼接容器）
    → 遍历所有段落paragraph，非空文本追加进markdown
    → 遍历文档内部资源关系rels，筛选图片资源
        → 取出图片二进制blob
        → 上传图片到MinIO，拿到minio_key + 公开url
        → 调用ocr_image识别图片文字
        → 构造ExtractedAsset存入assets列表
        → Markdown插入图片链接 + OCR文本块
    → 进度回调100%
    → 返回ParseResult
*TextParser:txt/md 原文包一层 # 标题（ UTF-8 解码，加 # 文件名 标题）*
    二进制 → utf8 文本 → 包一层 markdown 标题，返回
    
*Csv/ExcelParser:表格 → Markdown 表格*
1. 将文件二进制包装为内存虚拟文件，加载 xlsx 工作簿；
2. 循环遍历每一个工作表 Sheet：
    1. 读取第一行作为表头；Sheet 为空则直接标记空 Sheet；
    2. 表头转义处理，空表头自动填充「列 1、列 2…」；
    3. 逐行读取数据，标准化每行单元格；
    4. 判断是否超出最大行限制，超出则截断；
    5. 生成 Markdown 表格，追加截断提示（如截断）；
    6. 记录当前 sheet 元信息；
    3. 全部 Sheet 处理完成后关闭工作簿，释放文件资源；
4. 拼接全部 Markdown 片段，返回`(markdown文本, 元数据dict)`。
*ImageParser:OCR（ 调 OCR provider）* 
1. 接收图片二进制`file_data`，解析文件后缀，匹配图片 MIME 类型；
2. 将原图上传 MinIO 对象存储，拿到存储 key 和访问链接；
3. 调用多模态 OCR 接口识别图片文字；
4. 构造`ExtractedAsset`资源对象，记录图片存储信息与 alt 描述；
5. 组装 Markdown 文档：包含图片 markdown 链接 + OCR 识别文字；
6. 返回`ParseResult`：markdown 文本、assets 图片资源、解析元数据。
*AudioParser:ASR → 转写 MD（未完成）*
*VideoParser:ffmpeg 分片 + 抽帧 VL + 音轨 ASR*
1. 接收视频二进制，写入临时目录；
2. ffprobe 探测视频元信息，校验总时长；
3. 将完整视频切分为多个时间分片；
4. 遍历每一个分片：
   1. 更新解析进度；
   2. 提取关键帧，调用 VL 生成画面理解摘要；
   3. 如果存在音轨，提取 wav 音频，调用 ASR 转写语音文本；
   4. 将分片时间、画面摘要、语音文本写入 Markdown；
5. 全部分片处理完成；临时目录自动删除；
6. 返回 Markdown 文本与解析元数据。

3.解析完成后就可以进行审核，审核通过后，发消息给交换机。document.vector.queue,document.graph.queue,两个消费者收到交换机投递消息后，vector_consumer和graph_comsumer并行执行。
vector_consumer：读 MinIO content.md,分块+embedding+ES。vector_done = true
1.读 MinIO content.md
2.分块 split_text：默认每500字符截取一次，overlap设置为50,尽量找段落，防止关键点截断
3.Embedding每段chunk向量化（text-embedding-v4），10条批量向量化，维度为1024
4.存入PostgreSQL(pgvector)，将向量化后的值存入到document_chunk表里的embedding值里
5.写Elasticsearch(BM25)
    先 INSERT PG 拿 chunk_id → 再将拿到的chunk_id,title,content写 ES(方便后续删数据之类可以找到对应的id) → 存入ES后返回es_doc_id，把 ES 文档 ID 存回 document_chunks.es_doc_id。

graph_consume等PG里有chunks，LLM抽实体->Neo4j。graph_done = true
先轮训查数据库里是否有分块数据，等到有分块好了存数据库后
调用LLM 从每个 chunk 抽 JSON(使用prompt，具体执行函数是extract_and_store) → 抽出来的json，将其中entities和relations用 Cypher 写入 Neo4j
两者都 true → status = ready

4.审核完成后，聊天就可以检索到，聊天问了一个问题后，langgraph的analyze就会判断是否为复杂问题，寒暄不检索直接回答，需要hybrid就走两路检索召回然后生成回答，复杂问题就rewrite拆分问题，判断要不要graph,为false则走rewrite → hybrid → merge → generate，need_graph为true则走rewrite → hybrid → graph → generate。
然后记忆的话则是每次回答同时查redis和memo0,redis的话先去查有没有记录，有的话塞到prompt进行回答，没有的话去qa_messages,qa_sessions进行查询，取出最近8轮存到redis里，同时塞到prompt里进行回答，每次新对话后都会把数据存到redis和postgreSQL里，同时异步用memo0通过llm抽取事实入库。

复杂度判断是在ANALYZE_PROMPT里面,给他定规则:
1. 寒暄/感谢/与知识库无关 → intent=chitchat, needs_hybrid=false, needs_graph=false
2. 单个事实、定义、数值 → fact_lookup + simple，通常只需 hybrid
3. 问两个实体关系、组织架构 → entity_relation + medium，needs_graph=true
4. 「A 的 B 的 C」、跨文档推理 → multi_hop + complex，needs_rewrite=true, needs_graph=true
5. 对比/汇总类 → compare|summarize + complex，needs_rewrite=true
6. 有对话记忆且问题含「刚才/上面/它」→ needs_rewrite=true

rewrite:
REWRITE_PROMPT = """你是检索 query 优化器。根据对话记忆，将用户问题改写为 1~3 条独立、可检索的搜索 query。

输出 JSON：
{"queries": ["query1", "query2"]}

要求：
- 补全指代（「它」「刚才那个流程」）
- 复杂对比题拆成多条
- 每条 query 自洽，不依赖上下文
- 不要编造实体名

只返回 JSON。""" 

hybrid:
    ES 关键词（BM25）+ PG 向量（pgvector）双路召回 → RRF 融合 → Rerank 精排
PG 向量（pgvector）：先将用户问题向量化embed_text,然后查询数据库,用pg_vector内置函数cosine_distance来找出余弦相近的数据，返回一个`ChunkHit`对象
ES 关键词（BM25）：执行retrieve_chunks函数，里面调用es_client.search()
    查询语句: bool_query: dict = {
        "must": [{"match": {"content": query}}], # 参与相关性评分
    }
RRF: 执行rrf_fuse函数，用融合公式从各20条中选出top_n(项目中是10)
rerank: 执行rerank_hits函数，用qwen3-rerank模型精排，选出前5条给大模型

graph：
1. 在 Neo4j 里找所有 Entity.name 被问题字符串包含 的节点（子串匹配，不是向量）
2. 作为种子，沿 RELATES_TO 走 1～2 hop
3. 丢掉「没走出邻居」的；优先短路径（1 跳排前面）；最多 20 条 -> 返回结果

**数据库表设计**
*documents*&*document_chunks*:
documents 和 document_chunks 是一对多。
ducuments存了文档的元数据，minIO路径，minIOkey，解析状态和审核状态。
document_chunks存储每个分块文档的所属文档的id，embedding,es里的id，方便混合检索和删除。

*qa_sessions、qa_messages*:
qa_sessions 和 qa_messages，一对多
qa_sessions存放每次对话的标题，属于哪个用户，创建时间
qa_messages存放所有对话的内容，这段消息属于哪段对话，消息内容，时间，role
*为什么拆 session / message，不合成一张？*
列表展示会话、权限按 user 过滤会话，和「拉某个会话的全部消息」是两种访问模式。拆开索引清晰，也符合聊天产品习惯。

*users、departments、roles、user_roles*:
*users（账号）*
用户名、邮箱、密码哈希，可选挂一个 department_id。
密码只存哈希；用户名/邮箱唯一。人是权限的主体，上传文档的 owner、审核人、会话归属都指向 user。

*departments（组织）*
很薄：部门名。
用户属于部门，文档也可以标部门。后面做「部门内可见」时，靠的就是这个归属，而不是把部门名写死在用户字符串里。

*roles（角色定义）*
角色名唯一，比如 admin。
角色表示能力/身份（能不能审文档、是不是超管），不表示「看到哪份文件」——看到哪份由文档可见性 + 部门决定。

*user_roles（人 ↔ 角色）*
纯多对多中间表：user_id + role_id 联合主键。
一个人可以多个角色，后面加 editor、viewer 也不用改用户表结构。


**技术选型**
这是一个企业知识库：要解决文档集中管理、跨格式解析、混合检索和复杂问题推理。
架构上我拆成 接入层 → 异步解析/索引流水线 → 多引擎存储 → Agentic RAG 问答；选型原则是 各存所长、异步解耦、检索可组合。
API层：FastAPI + JWT
异步友好，和 Python AI 生态一致；JWT 无状态，方便鉴权
主库：PostgreSQL + pgvector
业务事务 + 向量同库，权限过滤和回表简单；不必一上来上独立向量库
关键词：Elasticsearch BM25
专名、制度编号、精确词向量弱，BM25 补；和向量做混合
图谱：Neo4j
多跳关系是图遍历，比 PG 递归 CTE 更合适
文件：MinIO
大对象出库，PG 只存 key
队列：RabbitMQ
解析/向量/图谱异步；light/heavy 分流，视频不堵 PDF
缓存记忆：Redis（+ 可选 Mem0）
会话窗口低延迟；持久对话仍在 PG
编排：LangGraph
按意图路由 hybrid / rewrite / graph，比写死一条链灵活
观测：LangFuse（+ 本地 LangSmith）
线上 trace 成本与召回；开发调试用 Smith

**架构设计**
客户端
  → FastAPI（鉴权 / 上传 / 审核 / 问答 SSE）
       │
       ├─ 上传：MinIO raw + PG documents → MQ 解析（light/heavy）
       │     parse → MD 回 MinIO → 待审核
       │
       ├─ 审核通过：fanout → vector_queue + graph_queue（并行）
       │     vector：切块 → embedding → PG + ES
       │     graph：等 chunks → LLM 抽实体 → Neo4j
       │     双 done → status=ready
       │
       └─ 问答：Agentic RAG
             analyze → [rewrite] → hybrid(BM25+向量+RRF+Rerank)
                      → [graph 多跳] → generate
             记忆：Redis 短 + PG 会话；权限在检索前过滤

**技术选型和架构设计面试回答**
原来的资料，还会有些技术文档，普通搜索只能搜关键词，容易搜不准，所以做这个知识库，可以把多格式文档收进来，解析，建索引。因为PostgreSQL+pgvector支持向量数据类型，而向量化和BM25稀疏词权重高的检索特点互补。所以选用ELasticsearch做关键词检索。有些关系型的问题可能需要Neo4j来支持多跳查询。文件比较大，用minIO存原文和解析后的md文档，库里存他们的路径。一些大文件的解析，向量化，抽图谱可能会比较耗时，所以用RabbitMQ异步做，避免堵塞主进程。接口用 FastAPI，跟 Python 的 AI 组件好接；问答编排用Langgraph，先判断问题类型，再决定要不要改写，检索路径。绘画热数据存redis，完整对话存pg，memo0负责跨会话长期记忆。

**检索时怎么限制文档权限访问的**
documents.owner_id：文档上的「上传者是谁」
owner_ids：检索时「允许搜哪些人的文档」
先通过jwt得到current_user，然后去找当前用户能访问文档的owner_id塞到owner_ids里，检索的时候带上owner_ids,保证检索到的文档的owner_id属于owner_ids


**明天的任务，把几个面试文档也上传到github**