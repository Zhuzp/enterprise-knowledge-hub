from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略 LANGFUSE_* 等未声明变量
    )

    # 数据库
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_database: str

    # JWT
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str = "documents"
    minio_secure: bool = False

    # 上传限制
    max_upload_size_mb: int = 50
    allowed_file_types: str = "pdf,docx,md,txt"  # 逗号分隔

    # ElasticSearch
    es_host: str = "http://127.0.0.1:9200"
    es_index: str = "documents"
    chunk_size: int = 500  # 每块大约 500 字符
    chunk_overlap: int = 50  # 块之间重叠 50 字符

    # LLM（OpenAI 兼容接口，可接 DeepSeek / 通义等）
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    rag_top_k: int = 5  # RAG 检索返回几条 chunk

    # Redis
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "document.published"
    rabbitmq_vector_queue: str = "document.vector.queue"
    rabbitmq_graph_queue: str = "document.graph.queue"

    # RabbitMQ — 解析（新增）
    rabbitmq_exchange_uploaded: str = "document.uploaded"
    rabbitmq_parse_light_queue: str = "document.parse.light.queue"
    rabbitmq_parse_heavy_queue: str = "document.parse.heavy.queue"

    # Embedding / Hybrid 检索
    embedding_model: str = "text-embedding-v4"
    embedding_dims: int = 1024
    recall_top_k: int = 20
    rrf_k: int = 60
    rrf_top_n: int = 10
    
    graph_recall_enabled: bool = True


    # Rerank（DashScope 独立 compatible-api 端点，与 chat/embedding 不同）
    rerank_model: str = "qwen3-rerank"
    rerank_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    rerank_top_n: int = 5
    rerank_enabled: bool = True

    # LangSmith（LangChain 从 os.environ 读取，启动时同步）
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "enterprise-knowledge-hub"
    langchain_environment: str = "development"

    # settings.py 追加
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 短期记忆
    memory_window_size: int = 8          # 保留最近 8 轮（16 条消息）
    memory_summary_trigger: int = 12     # window 超过 12 条时触发摘要
    memory_session_ttl_seconds: int = 259200  # Redis 3 天过期

    # Mem0 长期记忆
    mem0_enabled: bool = False
    mem0_top_k_user: int = 3
    mem0_top_k_session: int = 2

    # 审核策略
    review_require_parsed: bool = True   # 未解析完不允许 approve

    # 解析路由
    parse_heavy_file_types: str = "mp4,mov,avi,mkv,mp3,wav,m4a,flac"

    # MinIO 公开 URL（Markdown 里图片链接）
    minio_public_base_url: str = "http://127.0.0.1:9000/documents"

    # 上传大小
    max_upload_size_mb: int = 50
    max_media_upload_size_mb: int = 500

    allowed_file_types: str = "pdf,docx,md,txt,png,jpg,jpeg,webp,mp3,wav,m4a,mp4,mov"

    # 音视频解析
    asr_model: str = "paraformer-v2"
    asr_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    video_model: str = "qwen-vl-max-latest"
    video_segment_seconds: int = 300          # 每 5 分钟一段
    video_max_duration_seconds: int = 7200    # 单文件最长 2 小时
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    # OCR（图片 / 视频帧，若已有可复用）
    ocr_model: str = "qwen-vl-ocr-latest"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def allowed_extensions(self) -> set[str]:
        return {f".{ext.strip()}" for ext in self.allowed_file_types.split(",")}


def _sync_langsmith_env() -> None:
    """把 .env 中的 LangSmith 配置同步到 os.environ，供 LangChain 自动 tracing"""
    import os

    if settings.langchain_tracing_v2:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
    else:
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    if settings.langchain_project:
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    if settings.langchain_environment:
        os.environ["LANGCHAIN_ENVIRONMENT"] = settings.langchain_environment


settings = AppSettings()
_sync_langsmith_env()
