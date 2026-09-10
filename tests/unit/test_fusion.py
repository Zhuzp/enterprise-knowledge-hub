"""RRF 融合检索"""

from app.ai.retrievers.fusion import rrf_fuse
from app.ai.retrievers.schemas import ChunkHit


def _hit(chunk_id: int, rank: int, source: str = "bm25") -> ChunkHit:
    return ChunkHit(
        chunk_id=chunk_id,
        document_id=1,
        title="doc",
        content=f"chunk-{chunk_id}",
        score=1.0,
        source=source,
        rank=rank,
    )


def test_rrf_fuse_promotes_items_in_both_lists():
    bm25 = [_hit(1, 1), _hit(2, 2)]
    vector = [_hit(2, 1), _hit(3, 2)]
    fused = rrf_fuse([bm25, vector], k=60, top_n=3)
    ids = [h.chunk_id for h in fused]
    assert ids[0] == 2  # 两路都出现，RRF 分最高
    assert set(ids) == {2, 1, 3}


def test_rrf_fuse_respects_top_n():
    lists = [[_hit(i, i) for i in range(1, 6)]]
    fused = rrf_fuse(lists, top_n=2)
    assert len(fused) == 2
