"""Agentic RAG 状态与路由决策模型"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict

from app.ai.memory.schemas import MemoryContext


class Intent(StrEnum):
    CHITCHAT = "chitchat"           # 寒暄、感谢，无需检索
    FACT_LOOKUP = "fact_lookup"     # 单点事实：「报销上限是多少」
    ENTITY_RELATION = "entity_relation"  # 实体关系：「A 和 B 什么关系」
    MULTI_HOP = "multi_hop"         # 多跳：「A 的上级的部门负责什么政策」
    COMPARE = "compare"             # 对比：「X 和 Y 流程有何不同」
    SUMMARIZE = "summarize"         # 汇总：「培训视频都讲了哪些要点」


class Complexity(StrEnum):
    SIMPLE = "simple"       # 一次检索够
    MEDIUM = "medium"       # 需要改写或图谱
    COMPLEX = "complex"     # 改写 + 多工具


class RoutePath(StrEnum):
    DIRECT = "direct"
    HYBRID = "hybrid"
    GRAPH = "graph"
    FULL = "full"


class RouteDecision(BaseModel):
    """analyze 节点输出，驱动条件路由"""
    intent: Intent
    complexity: Complexity
    path: RoutePath
    needs_hybrid: bool = True
    needs_graph: bool = False
    needs_rewrite: bool = False
    reasoning: str = Field(default="", description="路由理由，便于 LangSmith 观测")


class AgenticRAGState(TypedDict):
    question: str
    owner_ids: list[int] | None
    memory: NotRequired[MemoryContext | None]

    # analyze 产出
    route_decision: NotRequired[RouteDecision | None]

    # rewrite 产出
    rewritten_queries: NotRequired[list[str]]

    # 检索产出
    chunks: NotRequired[list[dict[str, Any]]]
    graph_reasoning: NotRequired[str]          # 图谱推理链文本
    context: NotRequired[str]

    answer: NotRequired[str]