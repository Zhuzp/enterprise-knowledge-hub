from app.infra.neo4j_client import run_query


def expand_entities_from_question(question: str, limit: int = 10) -> list[str]:
    """从问题中匹配已有实体，扩展关联实体名"""
    results = run_query(
        """
        MATCH (e:Entity)
        WHERE $question CONTAINS e.name
        MATCH (e)-[:RELATES_TO*1..2]-(related:Entity)
        RETURN DISTINCT related.name AS name
        LIMIT $limit
        """,
        {"question": question, "limit": limit},
    )
    return [r["name"] for r in results]


def expand_query(question: str) -> str:
    related = expand_entities_from_question(question)
    if not related:
        return question
    return question + " " + " ".join(related)