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
    # 使用openpyxl加载内存中的xlsx文件
    # BytesIO：把二进制bytes包装成内存虚拟文件，不需要写入磁盘
    # read_only=True：只读模式，大文件流式读取，节省内存
    # data_only=True：读取单元格【计算后的值】，而不是公式文本
    wb = load_workbook(io.BytesIO(file_data), read_only=True, data_only=True)
    # 从配置读取：单个Sheet最多读取多少行，防止超大表格撑爆内存（这里设置500）
    max_rows = settings.spreadsheet_max_rows_per_sheet
    # 用列表收集markdown片段（字符串拼接用list更高效，减少字符串频繁拷贝）
    # 第一行是一级标题：# 文件名
    parts = [f"# {file_name}\n"]
    # 保存所有sheet的元信息，最后放到返回metadata，用于日志、监控、langfuse
    sheet_meta = []
    # 循环遍历Excel里面每一个工作表（Sheet1/Sheet2...）
    for sheet in wb.worksheets:
        # iter_rows生成器，逐行读取sheet；values_only=True 直接拿到单元格的值，不要单元格对象
        rows_iter = sheet.iter_rows(values_only=True)
        # 取出迭代器第一行，作为表头；如果sheet为空，返回None，不会抛异常
        first_row = next(rows_iter, None)
        # 判断：第一行是空 → 当前sheet是空工作表
        if not first_row:
            # markdown追加二级标题，标注这是空sheet
            parts.append(f"\n## Sheet: {sheet.title}\n\n（空 Sheet）\n")
            # 记录元数据：sheet名称，行数0
            sheet_meta.append({"name": sheet.title, "row_count": 0})
            continue
        # 处理表头：逐个转义单元格内容，防止 | 破坏markdown表格
        # 如果表头单元格为空，自动命名为 列1、列2、列3……
        headers = [_escape_cell(h) or f"列{i+1}" for i, h in enumerate(first_row)]
        # 获取表头总列数，后续所有数据行都对齐这个列数
        col_count = len(headers)
        # 用来存放处理之后的数据行（二维数组）
        data_rows: list[list[str]] = []
        # 遍历剩下所有数据行
        for row in rows_iter:
            # _normalize_row：转义单元格 + 补齐/截断列，保证每行和表头列数一致
            data_rows.append(_normalize_row(list(row), col_count))
        # 判断：当前读到的数据行数是否超过配置上限
        truncated = len(data_rows) > max_rows
        if truncated:
            # 超过上限，只保留前面max_rows行，后面全部丢弃
            data_rows = data_rows[:max_rows]
        # 调用工具函数，把表头+数据行生成markdown表格字符串
        table = _rows_to_markdown_table(headers, data_rows)
        # 将当前sheet的二级标题 + 表格，追加到markdown片段列表
        parts.append(f"\n## Sheet: {sheet.title}\n\n{table}\n")
        # 如果发生了行数截断，追加提示文本告诉模型/用户：只展示部分行
        # ⚠️这里有bug：截断后已经不知道原始总行数，只能写死“更多”
        if truncated:
            parts.append(f"> Sheet `{sheet.title}` 仅展示前 {max_rows} 行，共 {len(data_rows) if not truncated else '更多'} 行。\n")
        # 记录当前sheet元信息：sheet名字、最终保留行数、是否截断
        sheet_meta.append({
            "name": sheet.title,
            "row_count": len(data_rows),
            "truncated": truncated,
        })
    # 关闭工作簿，释放资源；read_only模式下必须手动close，防止句柄泄漏
    wb.close()
    # 把所有markdown片段拼接成完整字符串
    # 返回二元组：(完整markdown文本, 解析元数据字典)
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