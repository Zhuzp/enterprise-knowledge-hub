"""Agent 工具：chunk 合并与 context 拼接"""

from app.ai.agents.tools import chunks_to_context, merge_chunks


def _chunk(chunk_id: int, title: str = "制度手册") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": 1,
        "title": title,
        "content": f"内容-{chunk_id}",
        "score": 0.9,
        "source": "hybrid",
    }


def test_merge_chunks_deduplicates_by_chunk_id():
    a = [_chunk(1), _chunk(2)]
    b = [_chunk(2), _chunk(3)]
    merged = merge_chunks(a, b)
    assert [c["chunk_id"] for c in merged] == [1, 2, 3]


def test_chunks_to_context_includes_graph_reasoning_and_sources():
    ctx = chunks_to_context(
        [_chunk(10)],
        graph_reasoning="张三 → 负责 → 财务部",
    )
    assert "张三 → 负责 → 财务部" in ctx
    assert "制度手册" in ctx
    assert "内容-10" in ctx
    assert "(hybrid)" in ctx
