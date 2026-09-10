"""图谱推理：多跳关系链 + 关联 chunk 召回"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrievers.schemas import ChunkHit
from app.infra.neo4j_client import run_query
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk

# 多跳推理链：匹配问题中的实体 → 找 1~2 跳 RELATES_TO → 关联文档 chunk
# ---------------------- Cypher语句1：多跳关系查询 ----------------------
# 1. 匹配问题文本中包含的实体作为种子节点 seed
# 2. 做1~2跳 RELATES_TO 关系遍历
# 3. 返回：源实体、目标实体、关系类型、跳数
MULTI_HOP_CYPHER = """
MATCH (e:Entity)
WHERE $question CONTAINS e.name
WITH collect(DISTINCT e) AS seeds
UNWIND seeds AS seed
OPTIONAL MATCH path = (seed)-[:RELATES_TO*1..2]-(related:Entity)
WITH seed, related, relationships(path) AS rels
WHERE related IS NOT NULL
RETURN seed.name AS source,
       related.name AS target,
       [r IN rels | type(r)] AS rel_types,
       length(rels) AS hops
ORDER BY hops
LIMIT $limit
"""

# ---------------------- Cypher语句2：根据实体，找到关联的chunk_id ----------------------
# 实体 e 和文档块之间有 MENTIONS 关系，属性存 chunk_id
# 拿到这些 chunk_id，后面去PostgreSQL拿真实文档内容
CHUNK_BY_ENTITY_CYPHER = """
MATCH (e:Entity)
WHERE e.name IN $names
MATCH (d:Document)-[m:MENTIONS]->(e)
WHERE m.chunk_id IS NOT NULL
RETURN DISTINCT m.chunk_id AS chunk_id, e.name AS entity
LIMIT $limit
"""

# 返回结果数据类：推理文本 + 文档片段列表
@dataclass
class GraphReasonResult:
    reasoning_text: str
    chunk_hits: list[ChunkHit]

# 把Neo4j返回的关系行，格式化成人类可读的推理字符串
def _format_paths(rows: list[dict]) -> str:
    if not rows:
        return "（未在知识图谱中匹配到实体关系）"
    lines = ["【图谱推理链】"]
    for r in rows:
        rels = r.get("rel_types") or ["RELATES_TO"]
        rel_str = " → ".join(rels) if rels else "RELATES_TO"
        lines.append(f"- {r['source']} —[{rel_str}]→ {r['target']} ({r.get('hops', 1)} 跳)")
    return "\n".join(lines)


async def graph_reason(
    db: AsyncSession,
    question: str,
    owner_ids: list[int] | None,
    top_k: int = 5,
) -> GraphReasonResult:
    # 1. 执行多跳Cypher，查询实体关系
    # neo4j驱动是同步库，放到to_thread线程里面跑，不阻塞async事件循环
    path_rows = await asyncio.to_thread(
        run_query,
        MULTI_HOP_CYPHER,
        {"question": question, "limit": 20},
    )
    reasoning_text = _format_paths(path_rows)

    # 收集所有命中的实体名称（源实体、目标实体）
    entity_names = list({r["source"] for r in path_rows} | {r["target"] for r in path_rows})
    # 图谱没有找到任何实体，直接返回，没有文档
    if not entity_names:
        return GraphReasonResult(reasoning_text=reasoning_text, chunk_hits=[])

    # 2. 根据实体名称，查询Neo4j，拿到关联的chunk_id集合
    chunk_rows = await asyncio.to_thread(
        run_query,
        CHUNK_BY_ENTITY_CYPHER,
        {"names": entity_names, "limit": top_k * 3},
    )
    chunk_ids = list({int(r["chunk_id"]) for r in chunk_rows})
    # 3. 拿着chunk_id，去PostgreSQL数据库查询真实文档块内容、标题
    stmt = (
        select(DocumentChunk, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.id.in_(chunk_ids))
        .where(Document.status == DocumentStatus.READY.value)
    )
    # 权限过滤：只返回owner_ids有权限的文档
    if owner_ids is not None:
        stmt = stmt.where(Document.owner_id.in_(owner_ids))

    pg_rows = (await db.execute(stmt)).all()
    # 4. 组装 ChunkHit 对象列表
    hits: list[ChunkHit] = []
    for rank, (chunk, title) in enumerate(pg_rows, start=1):
        hits.append(
            ChunkHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=title,
                content=chunk.content,
                score=1.0 / rank,   # 简单打分：排名越靠前分数越高
                source="graph_reason",
                rank=rank,
            )
        )
        if len(hits) >= top_k:
            break

    return GraphReasonResult(reasoning_text=reasoning_text, chunk_hits=hits)