from langgraph.graph import END, START, StateGraph

from app.agents.cache_agent import CacheAgent
from app.agents.context_agent import ContextAgent
from app.agents.decision_agent import ComplexityAgent
from app.agents.generate_agent import GenerateAgent
from app.agents.quality_agent import QualityAgent
from app.agents.router_agent import RouterAgent
from app.orchestration.state import RequestState


cache_agent = CacheAgent()
complexity_agent = ComplexityAgent()
context_agent = ContextAgent()
router_agent = RouterAgent()
generate_agent = GenerateAgent()
quality_agent = QualityAgent()


def route_after_quality(state: RequestState) -> str:
    if (
        state.get("escalation")
        and not state.get("escalation_attempted")
        and state.get("actual_model") != "strong"
    ):
        return "escalate"
    return "end"


def prepare_escalation(state: RequestState) -> RequestState:
    state["escalation_attempted"] = True
    state["selected_model"] = "strong"
    state["routing_reason"] = (
        "Quality check failed; retrying with strong model"
    )
    return state


def build_graph():
    graph = StateGraph(RequestState)

    graph.add_node("cache", cache_agent.run)
    graph.add_node("complexity", complexity_agent.run)
    graph.add_node("context", context_agent.run)
    graph.add_node("router", router_agent.run)
    graph.add_node("generate", generate_agent.run)
    graph.add_node("quality", quality_agent.run)
    graph.add_node("prepare_escalation", prepare_escalation)

    graph.add_edge(START, "cache")
    graph.add_conditional_edges(
        "cache",
        lambda state: END if state.get("cached_response") else "complexity",
        {"complexity": "complexity", END: END},
    )
    graph.add_edge("complexity", "context")
    graph.add_edge("context", "router")
    graph.add_edge("router", "generate")
    graph.add_edge("generate", "quality")

    graph.add_conditional_edges(
        "quality",
        route_after_quality,
        {"escalate": "prepare_escalation", "end": END},
    )
    graph.add_edge("prepare_escalation", "generate")

    return graph.compile()


llm_graph = build_graph()