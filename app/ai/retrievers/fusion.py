from app.ai.retrievers.schemas import ChunkHit


def rrf_fuse(
    lists: list[list[ChunkHit]],
    k: int = 60,
    top_n: int = 10,
) -> list[ChunkHit]:
    scores: dict[int, float] = {}
    best: dict[int, ChunkHit] = {}

    for hits in lists:
        for hit in hits:
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0) + 1 / (k + hit.rank)
            if hit.chunk_id not in best:
                best[hit.chunk_id] = hit

    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [best[cid] for cid in sorted_ids[:top_n]]