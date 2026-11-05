"""Optional LangGraph driver; all security behavior stays in Runner.step."""
from typing import TypedDict


def execute(runner):
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError as e:
        raise RuntimeError("Install requirements-optional.lock for LangGraph") from e

    class State(TypedDict):
        done: bool

    def turn(state):
        runner.step()
        return {"done": runner.done}

    graph = StateGraph(State)
    graph.add_node("turn", turn)
    graph.add_edge(START, "turn")
    graph.add_conditional_edges("turn", lambda s: END if s["done"] else "turn")
    graph.compile().invoke({"done": False}, {"recursion_limit": 40})
