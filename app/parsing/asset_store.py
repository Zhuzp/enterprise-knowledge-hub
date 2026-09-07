"""解析过程中提取的图片/帧等资源上传 MinIO"""

from app.core.settings import settings
from app.infra.minio_client import upload_file


def build_asset_key(owner_id: int, doc_uuid: str, filename: str) -> str:
    return f"users/{owner_id}/{doc_uuid}/assets/{filename}"


def build_public_url(object_key: str) -> str:
    base = settings.minio_public_base_url.rstrip("/")
    return f"{base}/{object_key}"


def upload_asset(
    *,
    owner_id: int,
    doc_uuid: str,
    filename: str,
    data: bytes,
    content_type: str,
) -> tuple[str, str]:
    """上传资源，返回 (minio_key, public_url)"""
    object_key = build_asset_key(owner_id, doc_uuid, filename)
    upload_file(data, object_key, content_type)
    return object_key, build_public_url(object_key)
