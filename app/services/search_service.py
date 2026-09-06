from app.infra.es_client import search_documents
from app.schemas.search import SearchResponse, SearchResultItem


def do_search(query: str, owner_ids: list[int] | None, page: int, page_size: int) -> SearchResponse:
    result = search_documents(query, owner_ids, page, page_size)

    hits = result["hits"]["hits"]
    total = result["hits"]["total"]["value"]

    items = []
    for hit in hits:
        source = hit["_source"]
        highlight = None
        if "highlight" in hit and "content" in hit["highlight"]:
            highlight = hit["highlight"]["content"][0]

        items.append(
            SearchResultItem(
                document_id=source["document_id"],
                chunk_id=source["chunk_id"],
                title=source["title"],
                content=source["content"][:200],  # 截取前 200 字
                highlight=highlight,
                score=hit["_score"],
            )
        )

    return SearchResponse(query=query, total=total, items=items)
