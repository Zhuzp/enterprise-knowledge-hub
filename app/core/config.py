from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Enterprise Knowledge Hub"
    database_url: str = "postgresql://user:pass@localhost:5432/knowledge"
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"  # 从 .env 文件读配置


settings = Settings()
