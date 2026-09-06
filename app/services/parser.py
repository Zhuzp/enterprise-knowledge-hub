from io import BytesIO

from docx import Document as DocxDocument
from pypdf import PdfReader


def parse_pdf(file_data: bytes) -> str:
    """PDF → 纯文本"""
    reader = PdfReader(BytesIO(file_data))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def parse_docx(file_data: bytes) -> str:
    """Word → 纯文本"""
    doc = DocxDocument(BytesIO(file_data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def parse_text(file_data: bytes) -> str:
    """Markdown / TXT → 纯文本"""
    return file_data.decode("utf-8")


def parse_document(file_data: bytes, file_type: str) -> str:
    """根据文件类型选择解析器"""
    parsers = {
        "pdf": parse_pdf,
        "docx": parse_docx,
        "md": parse_text,
        "txt": parse_text,
    }
    parser = parsers.get(file_type)
    if parser is None:
        raise ValueError(f"不支持的文件类型: {file_type}")
    return parser(file_data)
