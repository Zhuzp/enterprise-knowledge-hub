from io import BytesIO
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from app.core.settings import settings

minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket_exists() -> None:
    """启动时确保 bucket 存在"""
    bucket = settings.minio_bucket
    if not minio_client.bucket_exists(bucket):
        minio_client.make_bucket(bucket)


def generate_object_key(owner_id: int, file_name: str) -> str:
    """生成 MinIO 存储路径：users/1/uuid_文件名.pdf"""
    unique_id = uuid4().hex[:8]
    return f"users/{owner_id}/{unique_id}_{file_name}"


def upload_file(file_data: bytes, object_key: str, content_type: str) -> None:
    """上传文件到 MinIO"""
    ensure_bucket_exists()
    minio_client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=object_key,
        data=BytesIO(file_data),
        length=len(file_data),
        content_type=content_type,
    )


def download_file(object_key: str) -> bytes:
    """从 MinIO 下载文件"""
    response = minio_client.get_object(settings.minio_bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(object_key: str) -> None:
    """从 MinIO 删除文件"""
    minio_client.remove_object(settings.minio_bucket, object_key)
