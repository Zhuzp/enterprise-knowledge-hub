from neo4j import GraphDatabase

from app.core.settings import settings

driver = GraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
)


def run_query(cypher: str, params: dict | None = None) -> list[dict]:
    with driver.session() as session:
        result = session.run(cypher, params or {})
        return [record.data() for record in result]


def init_constraints() -> None:
    """启动时创建唯一约束，防止重复节点"""
    run_query("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
    run_query("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")


def delete_document_graph(document_id: int) -> None:
    """删除文档相关的图谱数据"""
    run_query(
        """
        MATCH (d:Document {id: $doc_id})
        DETACH DELETE d
        """,
        {"doc_id": document_id},
    )


def close_driver() -> None:
    driver.close()