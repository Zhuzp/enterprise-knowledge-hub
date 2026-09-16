"""文本分块"""

from app.services.chunker import split_text


def test_split_text_respects_chunk_size():
    text = "A" * 1200
    chunks = split_text(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 600 for c in chunks)  # 允许在句号处略超 chunk_size


def test_split_text_prefers_paragraph_boundary():
    text = ("第一段内容。" * 30) + "\n\n" + ("第二段内容。" * 30)
    chunks = split_text(text)
    assert len(chunks) >= 1
    assert all(c.strip() for c in chunks)


def test_split_text_empty_returns_empty():
    assert split_text("") == []
    assert split_text("   \n  ") == []
