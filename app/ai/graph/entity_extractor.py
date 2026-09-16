import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.settings import settings
from app.infra.neo4j_client import run_query

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """你是企业知识库图谱抽取器。从用户给出的文本片段中抽取实体和关系。

【实体类型】
- Person：人员、角色
- Department：部门、团队、组织
- Policy：制度、流程、规章、办法
- Concept：业务概念、术语、指标
- Other：产品、系统、项目等专有名词

【关系规则】
- relations 的 source、target 必须出现在 entities 的 name 中
- type 用简短中文，如：属于、负责、审批、适用、包含、汇报给、管理
- 只抽文本中明确或可合理推断的关系，不要编造

【输出要求】
- 只返回 JSON，不要 markdown 或其它说明
- 无内容时：{"entities": [], "relations": []}

【JSON 格式】
{
  "entities": [{"name": "实体名", "type": "Person|Department|Policy|Concept|Other"}],
  "relations": [{"source": "实体A", "target": "实体B", "type": "关系类型"}]
}"""


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

    # 查找：有没有一个标签为`Document`、`id = $doc_id`的节点，有就复用，没有就新建
    run_query(
        """
        MERGE (d:Document {id: $doc_id})
        SET d.title = $title, d.owner_id = $owner_id
        """,
        {"doc_id": document_id, "title": title, "owner_id": owner_id},
    )

    # 实体 + MENTIONS 关系
    # LM 抽出来的每一个实体：- 实体不存在就新建；存在就复用；然后连一条边：**文档提到该实体**，并且记录来自哪个 chunk
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

    # LLM 抽出来的每一对实体关系：两个实体不存在就新建；存在就复用；在两个实体之间连一条关系边，记录这个关系来自哪篇文档
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