"""LangGraph 条件路由（不依赖外部服务）"""

from app.ai.agents.agentic_rag_graph import route_after_analyze, route_after_hybrid
from app.ai.agents.schemas import Complexity, Intent, RouteDecision, RoutePath


def _state(decision: RouteDecision) -> dict:
    return {"route_decision": decision}


def test_route_after_analyze_direct():
    d = RouteDecision(
        intent=Intent.CHITCHAT,
        complexity=Complexity.SIMPLE,
        path=RoutePath.DIRECT,
        needs_hybrid=False,
    )
    assert route_after_analyze(_state(d)) == "direct"


def test_route_after_analyze_hybrid_only():
    d = RouteDecision(
        intent=Intent.FACT_LOOKUP,
        complexity=Complexity.SIMPLE,
        path=RoutePath.HYBRID,
        needs_rewrite=False,
    )
    assert route_after_analyze(_state(d)) == "hybrid_only"


def test_route_after_analyze_rewrite_hybrid():
    d = RouteDecision(
        intent=Intent.COMPARE,
        complexity=Complexity.COMPLEX,
        path=RoutePath.HYBRID,
        needs_rewrite=True,
    )
    assert route_after_analyze(_state(d)) == "rewrite_hybrid"


def test_route_after_analyze_rewrite_full_for_graph():
    d = RouteDecision(
        intent=Intent.ENTITY_RELATION,
        complexity=Complexity.MEDIUM,
        path=RoutePath.GRAPH,
        needs_graph=True,
        needs_rewrite=True,
    )
    assert route_after_analyze(_state(d)) == "rewrite_full"


def test_route_after_hybrid_branches():
    with_graph = RouteDecision(
        intent=Intent.ENTITY_RELATION,
        complexity=Complexity.MEDIUM,
        path=RoutePath.GRAPH,
        needs_graph=True,
    )
    without_graph = RouteDecision(
        intent=Intent.FACT_LOOKUP,
        complexity=Complexity.SIMPLE,
        path=RoutePath.HYBRID,
        needs_graph=False,
    )
    assert route_after_hybrid(_state(with_graph)) == "graph"
    assert route_after_hybrid(_state(without_graph)) == "merge"
