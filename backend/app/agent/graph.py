"""LangGraph wiring for the agent loop.

START -> understand -> plan -> agent --(tool calls)--> policy --(needs approval)--> approval -> execute
                                  \\                         \\---------------------------------/   |
                                   \\--(no tool calls)--> finalize -> END            observe <-------/
observe: budget exhausted -> finalize | repeated errors -> plan (re-plan) | otherwise -> agent
"""

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    MAX_CONSECUTIVE_ERRORS,
    MAX_REDUNDANT_LOOKUPS,
    MAX_REPLANS,
    AgentDeps,
    AgentNodes,
)
from app.agent.state import AgentState


def build_graph(deps: AgentDeps, checkpointer):
    n = AgentNodes(deps)
    g = StateGraph(AgentState)
    g.add_node("understand", n.understand)
    g.add_node("plan", n.plan)
    g.add_node("agent", n.agent)
    g.add_node("policy", n.policy)
    g.add_node("approval", n.approval)
    g.add_node("execute", n.execute)
    g.add_node("finalize", n.finalize)

    g.add_edge(START, "understand")
    g.add_edge("understand", "plan")
    g.add_edge("plan", "agent")
    g.add_conditional_edges("agent", route_after_agent, {"policy": "policy", "finalize": "finalize"})
    g.add_conditional_edges("policy", route_after_policy, {"approval": "approval", "execute": "execute"})
    g.add_edge("approval", "execute")
    g.add_conditional_edges(
        "execute",
        lambda s: route_after_execute(s, deps.settings.agent_max_steps),
        {"agent": "agent", "plan": "plan", "finalize": "finalize"},
    )
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


def route_after_agent(state: AgentState) -> str:
    return "policy" if state.get("pending") else "finalize"


def route_after_policy(state: AgentState) -> str:
    return "approval" if any(c.get("approval_id") for c in state.get("pending", [])) else "execute"


def route_after_execute(state: AgentState, max_steps: int) -> str:
    """The 'observe' decision: continue, re-plan, or wrap up."""
    if state.get("step_count", 0) >= max_steps:
        return "finalize"
    # The model is re-running the same lookups instead of answering — wrap up now.
    if state.get("redundant_lookups", 0) >= MAX_REDUNDANT_LOOKUPS:
        return "finalize"
    if state.get("consecutive_errors", 0) >= MAX_CONSECUTIVE_ERRORS and state.get("replans", 0) < MAX_REPLANS:
        return "plan"
    return "agent"
