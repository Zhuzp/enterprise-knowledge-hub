"""解析器注册与媒体类型推断"""

import pytest

from app.parsing.registry import get_parser, infer_media_category


@pytest.mark.parametrize(
    "ext,expected",
    [
        ("pdf", "document"),
        ("png", "image"),
        ("mp3", "audio"),
        ("mp4", "video"),
        ("csv", "spreadsheet"),
        ("xlsx", "spreadsheet"),
    ],
)
def test_infer_media_category(ext, expected):
    assert infer_media_category(ext) == expected


def test_get_parser_known_types():
    assert get_parser("pdf").__class__.__name__ == "PdfParser"
    assert get_parser("CSV").__class__.__name__ == "CsvParser"


def test_get_parser_unknown_raises():
    with pytest.raises(ValueError, match="不支持"):
        get_parser("exe")
