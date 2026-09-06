from app.ai.retrievers.schemas import ChunkHit
from app.infra.es_client import retrieve_chunks


def recall_bm25(
    query: str,
    owner_ids: list[int] | None,
    top_k: int = 20,
) -> list[ChunkHit]:
    hits = retrieve_chunks(query, owner_ids, top_k=top_k)
    results: list[ChunkHit] = []
    for rank, h in enumerate(hits, start=1):
        results.append(
            ChunkHit(
                chunk_id=h["chunk_id"],
                document_id=h["document_id"],
                title=h["title"],
                content=h["content"],
                score=float(h.get("score") or 0),
                source="bm25",
                rank=rank,
            )
        )
    return results