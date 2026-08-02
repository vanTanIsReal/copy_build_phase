from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.agents.nodes.planner_node import planner_node
from src.agents.state import AgentState
from src.agents.tools import ALL_TOOLS


def route_after_planner(state: AgentState) -> str:
    """Route to tool execution, or end the run if the planner errored or has a final reply."""
    if state.get("error"):
        return END
    return tools_condition(state)


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", route_after_planner, {"tools": "tools", END: END})
    graph.add_edge("tools", "planner")

    return graph.compile(checkpointer=MemorySaver())


agent = build_graph()
