from typing import Any

from elasticsearch import Elasticsearch, NotFoundError

from app.core.settings import settings

es_client = Elasticsearch(settings.es_host)

INDEX_MAPPINGS = {
    "properties": {
        "document_id": {"type": "integer"},
        "chunk_id": {"type": "integer"},
        "owner_id": {"type": "integer"},
        "title": {"type": "text"},
        "content": {"type": "text", "analyzer": "standard"},
        "file_type": {"type": "keyword"},
    }
}


def ensure_index_exists() -> None:
    """创建 ES 索引（如果不存在）"""
    if not es_client.indices.exists(index=settings.es_index):
        es_client.indices.create(
            index=settings.es_index,
            mappings=INDEX_MAPPINGS,
        )


def index_chunk(
    chunk_id: int,
    document_id: int,
    owner_id: int,
    title: str,
    content: str,
    file_type: str,
) -> str:
    """索引一个 chunk 到 ES，返回 ES 文档 ID"""
    ensure_index_exists()
    es_doc_id = f"doc_{document_id}_chunk_{chunk_id}"
    es_client.index(
        index=settings.es_index,
        id=es_doc_id,
        document={
            "document_id": document_id,
            "chunk_id": chunk_id,
            "owner_id": owner_id,
            "title": title,
            "content": content,
            "file_type": file_type,
        },
    )
    return es_doc_id


def search_documents(
    query: str,
    owner_ids: list[int] | None,  # 改：原来是 owner_id: int
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    ensure_index_exists()
    from_index = (page - 1) * page_size
    bool_query: dict = {
        "must": [{"match": {"content": query}}],
    }
    if owner_ids is not None:  # admin 为 None → 不限制
        bool_query["filter"] = [{"terms": {"owner_id": owner_ids}}]
    response = es_client.search(
        index=settings.es_index,
        query={"bool": bool_query},
        from_=from_index,
        size=page_size,
        highlight={
            "fields": {"content": {}},
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
    )
    return response.body


def retrieve_chunks(query: str, owner_ids: list[int] | None, top_k: int = 5) -> list[dict[str, Any]]:
    """RAG 检索：返回 Top-K 相关 chunk"""
    # 1.幂等保证ES索引存在，不存在则创建
    ensure_index_exists()
    # 2.构造 bool 查询体
    bool_query: dict = {
        "must": [{"match": {"content": query}}], # 参与相关性评分
    }
    # 如果传了 owner_ids，追加 filter 权限过滤
    if owner_ids is not None:
        bool_query["filter"] = [{"terms": {"owner_id": owner_ids}}] # 只过滤，不评分
    # 3.执行ES搜索
    response = es_client.search(
        index=settings.es_index, # 目标索引名
        query={"bool": bool_query},
        size=top_k, # 返回前top_k条，默认5
    )
    # 4.解析ES返回结果
    chunks = []
    for hit in response.body["hits"]["hits"]:
        source = hit["_source"]
        chunks.append(
            {
                "document_id": source["document_id"],
                "chunk_id": source["chunk_id"],
                "title": source["title"],
                "content": source["content"],
                "score": hit["_score"],
            }
        )
    return chunks


def delete_document_chunks(document_id: int) -> None:
    """删除某文档的所有 ES 索引"""
    try:
        es_client.delete_by_query(
            index=settings.es_index,
            query={"term": {"document_id": document_id}},
        )
    except NotFoundError:
        pass
