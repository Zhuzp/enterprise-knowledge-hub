from app.parsing.parsers.base import BaseParser
from app.parsing.schemas import ParseResult

class TextParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        text = file_data.decode("utf-8", errors="ignore")
        md = f"# {file_name}\n\n{text}"
        return ParseResult(markdown=md, metadata={"parser": "text"})