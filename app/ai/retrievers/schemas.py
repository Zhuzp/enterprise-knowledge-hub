from dataclasses import dataclass, field


@dataclass
class ChunkHit:
    chunk_id: int
    document_id: int
    title: str
    content: str
    score: float
    source: str  # "bm25" | "pgvector" | "graph_reason"
    rank: int = 0

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "title": self.title,
            "content": self.content,
            "score": self.score,
            "source": self.source,
        }