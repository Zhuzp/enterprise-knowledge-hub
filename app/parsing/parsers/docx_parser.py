from io import BytesIO

from docx import Document as DocxDocument
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from app.parsing.asset_store import upload_asset
from app.parsing.parsers.base import BaseParser
from app.parsing.providers.ocr import ocr_image
from app.parsing.schemas import ExtractedAsset, ParseResult


class DocxParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        # BytesIO包装内存流，python-docx打开文档（不落地磁盘）
        doc = DocxDocument(BytesIO(file_data))
        # 初始化assets数组、md_parts列表（markdown拼接容器）
        assets: list[ExtractedAsset] = []
        md_parts = [f"# {file_name}\n"]

        # 遍历所有段落paragraph，非空文本追加进markdown
        for para in doc.paragraphs:
            if para.text.strip():
                md_parts.append(para.text)

        img_idx = 0
        # 遍历文档内部资源关系rels，筛选图片资源
        for rel in doc.part.rels.values():
            if rel.reltype != RT.IMAGE:
                continue
            img_idx += 1
            # 取出图片二进制blob
            img_bytes = rel.target_part.blob
            fname = f"img_docx_{img_idx:03d}.png"
            # 上传图片到MinIO，拿到minio_key + 公开url
            minio_key, url = upload_asset(
                owner_id=owner_id,
                doc_uuid=doc_uuid,
                filename=fname,
                data=img_bytes,
                content_type="image/png",
            )
            # 调用ocr_image识别图片文字
            ocr_text = await ocr_image(img_bytes)
            # 构造ExtractedAsset存入assets列表
            assets.append(
                ExtractedAsset(
                    asset_type="image",
                    minio_key=minio_key,
                    public_url=url,
                    alt_text=ocr_text[:200] if ocr_text else "",
                    source_ref=f"inline_{img_idx}",
                )
            )
            # Markdown插入图片链接 + OCR文本块
            md_parts.append(f"\n![inline-{img_idx}]({url})\n")
            if ocr_text:
                md_parts.append(f"\n> OCR: {ocr_text}\n")

        # 进度回调100%
        if progress_callback:
            await progress_callback(1.0, "done")

        # 返回ParseResult
        return ParseResult(
            markdown="\n".join(md_parts),
            assets=assets,
            metadata={"parser": "docx", "image_count": img_idx},
        )
