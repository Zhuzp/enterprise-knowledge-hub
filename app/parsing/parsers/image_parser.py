from pathlib import Path

from app.parsing.asset_store import upload_asset
from app.parsing.parsers.base import BaseParser
from app.parsing.providers.ocr import ocr_image
from app.parsing.schemas import ExtractedAsset, ParseResult

_IMAGE_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


class ImageParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        if progress_callback:
            await progress_callback(0.1, "ocr start")

        ext = Path(file_name).suffix.lstrip(".").lower() or "png"
        content_type = _IMAGE_MIME.get(ext, "image/png")
        asset_name = f"img_source.{ext}"

        # 将原图上传 MinIO 对象存储，拿到存储 key 和访问链接
        minio_key, url = upload_asset(
            owner_id=owner_id,
            doc_uuid=doc_uuid,
            filename=asset_name,
            data=file_data,
            content_type=content_type,
        )

        # 调用之前实现的多模态OCR，识别图片内文字
        ocr_text = await ocr_image(file_data, mime_type=content_type)

        # 进度回调：100%，OCR完成
        if progress_callback:
            await progress_callback(1.0, "ocr done")

        # 构造提取资源对象ExtractedAsset
        # alt_text取OCR文本前200字符，作为图片描述，给RAG/前端展示
        asset = ExtractedAsset(
            asset_type="image",
            minio_key=minio_key,
            public_url=url,
            alt_text=ocr_text[:200] if ocr_text else "",
            source_ref="source",
        )

        # 组装Markdown：一级标题 + markdown图片链接 + OCR文字章节
        md_parts = [f"# {file_name}\n", f"\n![{file_name}]({url})\n", "\n## OCR\n\n"]
        md_parts.append(ocr_text if ocr_text else "（未识别到文字）")

        # 返回统一ParseResult
        # markdown：生成的文档文本
        # assets：图片资源对象（存入资源列表，和PDF/Docx里提取图片逻辑一致）
        # metadata：标记解析器类型、OCR识别字符数量，用于日志/Langfuse
        return ParseResult(
            markdown="".join(md_parts),
            assets=[asset],
            metadata={"parser": "image", "ocr_chars": len(ocr_text)},
        ) 