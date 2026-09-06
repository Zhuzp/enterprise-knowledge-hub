import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrievers.schemas import ChunkHit
from app.infra.neo4j_client import run_query
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk

# 从问题里匹配 Entity → 扩展关联实体 → 找 Document-MENTIONS→Entity 上的 chunk_id
GRAPH_RECALL_CYPHER = """
MATCH (e:Entity)
WHERE $question CONTAINS e.name
OPTIONAL MATCH (e)-[:RELATES_TO*1..2]-(related:Entity)
WITH collect(DISTINCT e) + [x IN collect(DISTINCT related) WHERE x IS NOT NULL] AS ents
UNWIND ents AS ent
MATCH (d:Document)-[m:MENTIONS]->(ent)
WHERE m.chunk_id IS NOT NULL
RETURN m.chunk_id AS chunk_id, d.id AS document_id, count(*) AS hit_score
ORDER BY hit_score DESC
LIMIT $limit
"""


async def recall_graph(
    db: AsyncSession,
    query: str,
    owner_ids: list[int] | None,
    top_k: int = 20,
) -> list[ChunkHit]:
    """
    图谱第三路召回：
    1. Neo4j 按实体匹配得到 chunk_id 列表
    2. 回 PG 取 chunk 内容，并过滤 status=ready + owner 权限
    """
    # run_query 是同步的，放到线程池避免阻塞事件循环
    rows = await asyncio.to_thread(
        run_query,
        GRAPH_RECALL_CYPHER,
        {"question": query, "limit": top_k * 3},
    )
    if not rows:
        return []

    # 保持 Neo4j 返回的排序（hit_score 越高越靠前）
    chunk_ids: list[int] = []
    seen: set[int] = set()
    for row in rows:
        cid = int(row["chunk_id"])
        if cid in seen:
            continue
        seen.add(cid)
        chunk_ids.append(cid)

    stmt = (
        select(DocumentChunk, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.id.in_(chunk_ids))
        .where(Document.status == DocumentStatus.READY.value)
    )
    if owner_ids is not None:
        stmt = stmt.where(Document.owner_id.in_(owner_ids))

    pg_rows = (await db.execute(stmt)).all()
    chunk_map = {chunk.id: (chunk, title) for chunk, title in pg_rows}

    results: list[ChunkHit] = []
    for rank, cid in enumerate(chunk_ids, start=1):
        if cid not in chunk_map:
            continue
        chunk, title = chunk_map[cid]
        results.append(
            ChunkHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=title,
                content=chunk.content,
                score=1.0 / rank,
                source="graph",
                rank=rank,
            )
        )
        if len(results) >= top_k:
            break

    return results