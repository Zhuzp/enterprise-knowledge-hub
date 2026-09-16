import fitz

from app.parsing.asset_store import upload_asset
from app.parsing.parsers.base import BaseParser
from app.parsing.providers.ocr import ocr_image
from app.parsing.schemas import ExtractedAsset, ParseResult


class PdfParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        # fitz打开内存流PDF（不落地磁盘）
        doc = fitz.open(stream=file_data, filetype="pdf")
        assets: list[ExtractedAsset] = []
        md_parts = [f"# {file_name}\n"]
        page_count = doc.page_count
        
        # 遍历每一页
        for page_idx, page in enumerate(doc, start=1):
            # 更新解析进度回调
            if progress_callback:
                await progress_callback((page_idx - 1) / max(page_count, 1), f"page {page_idx}/{page_count}")

            # 提取页面文字，写入Markdown
            md_parts.append(f"\n## Page {page_idx}\n")
            text = page.get_text("text").strip()
            if text:
                md_parts.append(text)
            # 遍历页面内所有图片
            for img_idx, img in enumerate(page.get_images(full=True), start=1):
                # 提取图片二进bin
                xref = img[0]
                base = doc.extract_image(xref)
                img_bytes = base["image"]
                ext = base.get("ext") or "png"
                fname = f"img_p{page_idx:03d}_{img_idx:02d}.{ext}"
                # 上传图片到MinIO，拿到存储key + 访问url
                minio_key, url = upload_asset(
                    owner_id=owner_id,
                    doc_uuid=doc_uuid,
                    filename=fname,
                    data=img_bytes,
                    content_type=f"image/{ext}",
                )
                # OCR识别图片文字
                ocr_text = await ocr_image(img_bytes)
                # 存入assets资源对象（记录图片链接、OCR alt文本、来源页码）
                assets.append(
                    ExtractedAsset(
                        asset_type="image",
                        minio_key=minio_key,
                        public_url=url,
                        alt_text=ocr_text[:200] if ocr_text else "",
                        source_ref=f"page_{page_idx}",
                    )
                )
                # Markdown插入图片链接 + OCR注释块
                md_parts.append(f"\n![page{page_idx}-img{img_idx}]({url})\n")
                if ocr_text:
                    md_parts.append(f"\n> OCR: {ocr_text}\n")

        if progress_callback:
            await progress_callback(1.0, "done")

        return ParseResult(
            markdown="\n".join(md_parts),
            assets=assets,
            metadata={"parser": "pdf", "page_count": page_count, "image_count": len(assets)},
        )
