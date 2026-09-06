from pydantic import BaseModel


class SearchResultItem(BaseModel):
    document_id: int
    chunk_id: int
    title: str
    content: str
    highlight: str | None = None
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    items: list[SearchResultItem]
