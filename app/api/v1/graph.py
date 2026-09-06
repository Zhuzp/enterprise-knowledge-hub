from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user
from app.infra.neo4j_client import run_query
from app.models.user import User

router = APIRouter()


@router.get("/entities")
def list_entities(
    q: str = Query("", description="实体名关键词"),
    limit: int = Query(20, ge=1, le=100),
    _current_user: User = Depends(get_current_user),
):
    if q:
        return run_query(
            """
            MATCH (e:Entity)
            WHERE e.name CONTAINS $q
            RETURN e.name AS name, e.type AS type
            ORDER BY e.name
            LIMIT $limit
            """,
            {"q": q, "limit": limit},
        )
    return run_query(
        """
        MATCH (e:Entity)
        RETURN e.name AS name, e.type AS type
        ORDER BY e.name
        LIMIT $limit
        """,
        {"limit": limit},
    )


@router.get("/relations")
def list_relations(
    entity: str = Query(..., min_length=1, description="实体名"),
    depth: int = Query(1, ge=1, le=3),
    _current_user: User = Depends(get_current_user),
):
    # Neo4j 路径深度必须是字面量，不能用 $depth 参数
    cypher = f"""
        MATCH path = (e:Entity {{name: $entity}})-[r:RELATES_TO*1..{depth}]-(related:Entity)
        UNWIND relationships(path) AS rel
        RETURN DISTINCT
            startNode(rel).name AS source,
            type(rel) AS relation,
            rel.type AS relation_type,
            endNode(rel).name AS target
        LIMIT 50
        """
    return run_query(cypher, {"entity": entity})


@router.get("/visualize/{entity_name}")
def visualize(
    entity_name: str,
    depth: int = Query(2, ge=1, le=3),
    _current_user: User = Depends(get_current_user),
):
    """返回前端渲染用的 nodes + edges"""
    node_rows = run_query(
        f"""
        MATCH (e:Entity {{name: $name}})
        OPTIONAL MATCH path = (e)-[*1..{depth}]-(n)
        WHERE n IS NULL OR n:Entity OR n:Document
        WITH e, [x IN collect(DISTINCT n) WHERE x IS NOT NULL] AS connected
        UNWIND [e] + connected AS node
        RETURN
            elementId(node) AS id,
            labels(node)[0] AS type,
            properties(node) AS props
        """,
        {"name": entity_name},
    )

    edge_rows = run_query(
        f"""
        MATCH (e:Entity {{name: $name}})
        OPTIONAL MATCH path = (e)-[*1..{depth}]-(n)
        WHERE n:Entity OR n:Document
        UNWIND relationships(path) AS rel
        RETURN DISTINCT
            elementId(startNode(rel)) AS source,
            elementId(endNode(rel)) AS target,
            type(rel) AS rel_type,
            properties(rel) AS props
        """,
        {"name": entity_name},
    )

    if not node_rows:
        return {"nodes": [], "edges": []}

    nodes = []
    seen: set[str] = set()
    for row in node_rows:
        node_id = row["id"]
        if node_id in seen:
            continue
        seen.add(node_id)
        props = row.get("props") or {}
        nodes.append(
            {
                "id": node_id,
                "label": props.get("name") or props.get("title") or node_id,
                "type": row.get("type") or "Unknown",
                "properties": props,
            }
        )

    edges = []
    for row in edge_rows:
        if not row.get("source") or not row.get("target"):
            continue
        edges.append(
            {
                "source": row["source"],
                "target": row["target"],
                "type": row.get("rel_type") or "RELATES_TO",
                "properties": row.get("props") or {},
            }
        )

    return {"nodes": nodes, "edges": edges}
