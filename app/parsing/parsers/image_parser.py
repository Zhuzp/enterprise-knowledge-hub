# app/parsing/parsers/image_parser.py
from app.parsing.parsers.base import BaseParser
from app.parsing.providers.asr import transcribe_bytes  # 可换成 ocr.py
from app.parsing.schemas import ParseResult, ExtractedAsset
from app.parsing.asset_store import upload_asset  # 若未建，先跳过 assets

class ImageParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        # TODO: 调 OCR provider
        ocr_text = "（OCR 待实现）"
        md = f"# {file_name}\n\n## OCR\n\n{ocr_text}"
        return ParseResult(markdown=md, metadata={"parser": "image"}) 