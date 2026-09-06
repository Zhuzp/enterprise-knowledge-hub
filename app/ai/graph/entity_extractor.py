import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.settings import settings
from app.infra.neo4j_client import run_query

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """从以下文本中抽取实体和关系，以 JSON 返回：
{
  "entities": [{"name": "实体名", "type": "Person|Department|Policy|Concept|Other"}],
  "relations": [{"source": "实体A", "target": "实体B", "type": "关系类型"}]
}
只返回 JSON，不要其他内容。如果没有实体或关系，返回空数组。"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )


def extract_and_store(
    *,
    chunk_id: int,
    document_id: int,
    title: str,
    content: str,
    owner_id: int,
) -> None:
    """从 chunk 抽取实体/关系并写入 Neo4j"""
    llm = _get_llm()
    resp = llm.invoke([
        SystemMessage(content=EXTRACT_PROMPT),
        HumanMessage(content=content[:2000]),  # 控制 token 成本
    ])

    try:
        data = json.loads(resp.content)
    except json.JSONDecodeError:
        logger.warning("实体抽取 JSON 解析失败: doc=%s chunk=%s", document_id, chunk_id)
        return

    # 文档节点
    run_query(
        """
        MERGE (d:Document {id: $doc_id})
        SET d.title = $title, d.owner_id = $owner_id
        """,
        {"doc_id": document_id, "title": title, "owner_id": owner_id},
    )

    # 实体 + MENTIONS 关系
    for e in data.get("entities", []):
        name = e.get("name", "").strip()
        if not name:
            continue
        run_query(
            """
            MERGE (ent:Entity {name: $name})
            SET ent.type = $type
            WITH ent
            MATCH (d:Document {id: $doc_id})
            MERGE (d)-[:MENTIONS {chunk_id: $chunk_id}]->(ent)
            """,
            {
                "name": name,
                "type": e.get("type", "Other"),
                "doc_id": document_id,
                "chunk_id": chunk_id,
            },
        )

    # 实体间关系
    for r in data.get("relations", []):
        src = r.get("source", "").strip()
        dst = r.get("target", "").strip()
        if not src or not dst:
            continue
        run_query(
            """
            MERGE (a:Entity {name: $src})
            MERGE (b:Entity {name: $dst})
            MERGE (a)-[:RELATES_TO {type: $rel_type, doc_id: $doc_id}]->(b)
            """,
            {
                "src": src,
                "dst": dst,
                "rel_type": r.get("type", "related"),
                "doc_id": document_id,
            },
        )