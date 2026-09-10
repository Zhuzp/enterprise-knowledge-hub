"""pytest 全局 fixture：在导入 app 前注入测试环境变量。"""

import os

# pydantic-settings 在 import app 时即加载，必须先设 env
os.environ.setdefault("PG_HOST", "127.0.0.1")
os.environ.setdefault("PG_PORT", "5432")
os.environ.setdefault("PG_USER", "test")
os.environ.setdefault("PG_PASSWORD", "test")
os.environ.setdefault("PG_DATABASE", "test_db")
os.environ.setdefault("MINIO_ENDPOINT", "127.0.0.1:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
