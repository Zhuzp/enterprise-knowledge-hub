"""Excel / CSV → Markdown 表格"""

import csv
import io
from pathlib import Path

from openpyxl import load_workbook

from app.core.settings import settings
from app.parsing.parsers.base import BaseParser
from app.parsing.schemas import ParseResult


def _escape_cell(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
    return text.strip()


def _normalize_row(row: list, col_count: int) -> list[str]:
    cells = [_escape_cell(c) for c in row]
    if len(cells) < col_count:
        cells.extend([""] * (col_count - len(cells)))
    return cells[:col_count]


def _rows_to_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return "（空表）"

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _detect_csv_encoding(raw: bytes) -> str:
    """企业文件常见 utf-8-sig / gbk"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def _parse_csv_bytes(file_data: bytes, file_name: str) -> tuple[str, dict]:
    encoding = _detect_csv_encoding(file_data)
    text = file_data.decode(encoding, errors="replace")

    # 自动猜分隔符（逗号 / 制表符 / 分号）
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if not rows:
        md = f"# {file_name}\n\n（空 CSV 文件）"
        return md, {"parser": "csv", "encoding": encoding, "row_count": 0}

    headers = [_escape_cell(h) or f"列{i+1}" for i, h in enumerate(rows[0])]
    col_count = len(headers)
    max_rows = settings.spreadsheet_max_rows_per_sheet

    data_rows = [_normalize_row(r, col_count) for r in rows[1:]]
    truncated = len(data_rows) > max_rows
    if truncated:
        data_rows = data_rows[:max_rows]

    table = _rows_to_markdown_table(headers, data_rows)
    md = f"# {file_name}\n\n## 数据表\n\n{table}\n"
    if truncated:
        md += f"\n> 仅展示前 {max_rows} 行，共 {len(rows)-1} 行数据。\n"

    return md, {
        "parser": "csv",
        "encoding": encoding,
        "row_count": len(rows) - 1,
        "truncated": truncated,
    }


def _parse_xlsx_bytes(file_data: bytes, file_name: str) -> tuple[str, dict]:
    wb = load_workbook(io.BytesIO(file_data), read_only=True, data_only=True)
    max_rows = settings.spreadsheet_max_rows_per_sheet

    parts = [f"# {file_name}\n"]
    sheet_meta = []

    for sheet in wb.worksheets:
        rows_iter = sheet.iter_rows(values_only=True)
        first_row = next(rows_iter, None)
        if not first_row:
            parts.append(f"\n## Sheet: {sheet.title}\n\n（空 Sheet）\n")
            sheet_meta.append({"name": sheet.title, "row_count": 0})
            continue

        headers = [_escape_cell(h) or f"列{i+1}" for i, h in enumerate(first_row)]
        col_count = len(headers)

        data_rows: list[list[str]] = []
        for row in rows_iter:
            data_rows.append(_normalize_row(list(row), col_count))

        truncated = len(data_rows) > max_rows
        if truncated:
            data_rows = data_rows[:max_rows]

        table = _rows_to_markdown_table(headers, data_rows)
        parts.append(f"\n## Sheet: {sheet.title}\n\n{table}\n")
        if truncated:
            parts.append(f"> Sheet `{sheet.title}` 仅展示前 {max_rows} 行，共 {len(data_rows) if not truncated else '更多'} 行。\n")

        sheet_meta.append({
            "name": sheet.title,
            "row_count": len(data_rows),
            "truncated": truncated,
        })

    wb.close()
    return "\n".join(parts), {
        "parser": "xlsx",
        "sheet_count": len(sheet_meta),
        "sheets": sheet_meta,
    }


class CsvParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        if progress_callback:
            await progress_callback(0.2, "parse csv")
        md, meta = _parse_csv_bytes(file_data, file_name)
        if progress_callback:
            await progress_callback(1.0, "done")
        return ParseResult(markdown=md, metadata=meta)


class ExcelParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        if progress_callback:
            await progress_callback(0.2, "parse xlsx")

        suffix = Path(file_name).suffix.lower()
        if suffix == ".xls":
            raise ValueError("暂不支持旧版 .xls，请另存为 .xlsx 后上传")

        md, meta = _parse_xlsx_bytes(file_data, file_name)
        if progress_callback:
            await progress_callback(1.0, "done")
        return ParseResult(markdown=md, metadata=meta)