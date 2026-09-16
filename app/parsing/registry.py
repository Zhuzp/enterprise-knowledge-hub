from app.parsing.parsers.pdf_parser import PdfParser
from app.parsing.parsers.docx_parser import DocxParser
from app.parsing.parsers.spreadsheet_parser import CsvParser, ExcelParser
from app.parsing.parsers.text_parser import TextParser
from app.parsing.parsers.image_parser import ImageParser
from app.parsing.parsers.audio_parser import AudioParser
from app.parsing.parsers.video_parser import VideoParser

PARSER_REGISTRY = {
    "pdf": PdfParser,
    "docx": DocxParser,
    "md": TextParser,
    "txt": TextParser,
    "png": ImageParser,
    "jpg": ImageParser,
    "jpeg": ImageParser,
    "webp": ImageParser,
    "mp3": AudioParser,
    "wav": AudioParser,
    "m4a": AudioParser,
    "mp4": VideoParser,
    "mov": VideoParser,
    "csv": CsvParser,
    "xlsx": ExcelParser,
    "xls": ExcelParser,   # 注册但 parse 内会提示转 xlsx
}

def get_parser(file_type: str):
    cls = PARSER_REGISTRY.get(file_type.lower())
    if not cls:
        raise ValueError(f"不支持的文件类型: {file_type}")
    return cls()

# 根据**文件后缀名（不带点）**判断媒体分类
def infer_media_category(file_type: str) -> str:
    ft = file_type.lower()
    if ft in {"png", "jpg", "jpeg", "webp"}:
        return "image"
    if ft in {"mp3", "wav", "m4a", "flac"}:
        return "audio"
    if ft in {"mp4", "mov", "avi", "mkv"}:
        return "video"
    if ft in {"csv", "xlsx", "xls"}:
        return "spreadsheet"   # 可选：便于统计/展示
    return "document"