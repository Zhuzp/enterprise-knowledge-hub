"""CSV / Excel 解析 → Markdown"""

import pytest

from app.parsing.parsers.spreadsheet_parser import (
    CsvParser,
    ExcelParser,
    _parse_csv_bytes,
    _rows_to_markdown_table,
)
from openpyxl import Workbook
import io


def test_rows_to_markdown_table():
    md = _rows_to_markdown_table(["姓名", "部门"], [["张三", "研发"]])
    assert "| 姓名 | 部门 |" in md
    assert "| 张三 | 研发 |" in md
    assert "---" in md


def test_parse_csv_bytes_utf8():
    raw = "姓名,部门\n张三,研发\n".encode("utf-8")
    md, meta = _parse_csv_bytes(raw, "员工.csv")
    assert "张三" in md
    assert meta["parser"] == "csv"
    assert meta["row_count"] == 1


def test_parse_csv_bytes_gbk():
    raw = "姓名,部门\r\n李四,财务\r\n".encode("gbk")
    md, meta = _parse_csv_bytes(raw, "员工.csv")
    assert "李四" in md
    assert meta["encoding"] in ("gbk", "gb18030", "utf-8")


@pytest.mark.asyncio
async def test_csv_parser_async():
    parser = CsvParser()
    result = await parser.parse(
        file_data=b"a,b\n1,2\n",
        file_name="t.csv",
        owner_id=1,
        doc_uuid="uuid-1",
    )
    assert "1" in result.markdown
    assert result.metadata["parser"] == "csv"


@pytest.mark.asyncio
async def test_excel_parser_rejects_xls():
    parser = ExcelParser()
    with pytest.raises(ValueError, match="xls"):
        await parser.parse(
            file_data=b"fake",
            file_name="old.xls",
            owner_id=1,
            doc_uuid="uuid-2",
        )


@pytest.mark.asyncio
async def test_excel_parser_xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["项目", "金额"])
    ws.append(["差旅", 1000])
    buf = io.BytesIO()
    wb.save(buf)

    parser = ExcelParser()
    result = await parser.parse(
        file_data=buf.getvalue(),
        file_name="budget.xlsx",
        owner_id=1,
        doc_uuid="uuid-3",
    )
    assert "差旅" in result.markdown
    assert result.metadata["sheet_count"] == 1
