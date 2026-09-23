"""Production LangGraph wiring.

Builds the same state machine implemented (and actually tested) in
``runner.py``, using the identical node functions from ``nodes.py``, but
via a real ``langgraph.graph.StateGraph`` so RAG/SQL/tools genuinely run
concurrently (LangGraph's Pregel-style execution runs nodes with no
dependency between them in the same superstep) and the graph can be
visualized/traced through LangGraph's own tooling.

    START -> router -> {rag, sql, tools} -> diagnosis -> validation
                                                  ^            |
                                                  |            v
                                          (retry) <---- not valid, retries left
                                                              |
                                                validation -> safe_response -> END
                                                validation -> human_review -> END
"""

from __future__ import annotations

from functools import partial

from app.config import get_settings
from app.graph.deps import GraphDeps, default_deps
from app.graph.nodes import (
    diagnosis_node,
    human_review_node,
    rag_node,
    router_node,
    safe_response_node,
    sql_node,
    tools_node,
    validation_node,
)
from app.graph.state import GraphState


def _validation_router(state: GraphState) -> str:
    settings = get_settings()
    validation = state.get("validation", {})
    diagnosis = state.get("diagnosis", {})

    if validation.get("requires_human") and diagnosis.get("requires_human"):
        return "human_review"
    if validation.get("is_valid"):
        return "safe_response"

    retry_count = state.get("retry_count", 0)
    if retry_count >= settings.max_agent_retries:
        return "human_review"
    return "retry"


def _increment_retry(state: GraphState) -> dict:
    return {"retry_count": state.get("retry_count", 0) + 1}


def build_graph(deps: GraphDeps | None = None):
    """Compile the production graph. Requires the ``langgraph`` package
    (see requirements.txt); import is local so this module can still be
    imported (e.g. for inspection/tests of the surrounding wiring) in
    environments where langgraph isn't installed.
    """
    from langgraph.graph import END, START, StateGraph

    deps = deps or default_deps()
    graph = StateGraph(GraphState)

    graph.add_node("router", partial(router_node, deps=deps))
    graph.add_node("rag", partial(rag_node, deps=deps))
    graph.add_node("sql", partial(sql_node, deps=deps))
    graph.add_node("tools", partial(tools_node, deps=deps))
    graph.add_node("diagnosis", partial(diagnosis_node, deps=deps))
    graph.add_node("validation", partial(validation_node, deps=deps))
    graph.add_node("increment_retry", _increment_retry)
    graph.add_node("safe_response", partial(safe_response_node, deps=deps))
    graph.add_node("human_review", partial(human_review_node, deps=deps))

    graph.add_edge(START, "router")

    # Fan-out: RAG, SQL, and tools all run off the router with no
    # dependency on each other -- LangGraph executes them in the same
    # superstep (i.e. concurrently under the async/threaded runtime).
    graph.add_edge("router", "rag")
    graph.add_edge("router", "sql")
    graph.add_edge("router", "tools")

    # Fan-in: diagnosis only runs once rag/sql/tools have all completed.
    graph.add_edge("rag", "diagnosis")
    graph.add_edge("sql", "diagnosis")
    graph.add_edge("tools", "diagnosis")

    graph.add_edge("diagnosis", "validation")

    graph.add_conditional_edges(
        "validation",
        _validation_router,
        {
            "safe_response": "safe_response",
            "human_review": "human_review",
            "retry": "increment_retry",
        },
    )
    graph.add_edge("increment_retry", "diagnosis")

    graph.add_edge("safe_response", END)
    graph.add_edge("human_review", END)

    return graph.compile()
