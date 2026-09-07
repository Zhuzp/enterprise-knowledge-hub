from io import BytesIO

from docx import Document as DocxDocument
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from app.parsing.asset_store import upload_asset
from app.parsing.parsers.base import BaseParser
from app.parsing.providers.ocr import ocr_image
from app.parsing.schemas import ExtractedAsset, ParseResult


class DocxParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        doc = DocxDocument(BytesIO(file_data))
        assets: list[ExtractedAsset] = []
        md_parts = [f"# {file_name}\n"]

        for para in doc.paragraphs:
            if para.text.strip():
                md_parts.append(para.text)

        img_idx = 0
        for rel in doc.part.rels.values():
            if rel.reltype != RT.IMAGE:
                continue
            img_idx += 1
            img_bytes = rel.target_part.blob
            fname = f"img_docx_{img_idx:03d}.png"
            minio_key, url = upload_asset(
                owner_id=owner_id,
                doc_uuid=doc_uuid,
                filename=fname,
                data=img_bytes,
                content_type="image/png",
            )
            ocr_text = await ocr_image(img_bytes)
            assets.append(
                ExtractedAsset(
                    asset_type="image",
                    minio_key=minio_key,
                    public_url=url,
                    alt_text=ocr_text[:200] if ocr_text else "",
                    source_ref=f"inline_{img_idx}",
                )
            )
            md_parts.append(f"\n![inline-{img_idx}]({url})\n")
            if ocr_text:
                md_parts.append(f"\n> OCR: {ocr_text}\n")

        if progress_callback:
            await progress_callback(1.0, "done")

        return ParseResult(
            markdown="\n".join(md_parts),
            assets=assets,
            metadata={"parser": "docx", "image_count": img_idx},
        )
