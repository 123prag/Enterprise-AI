"""A dependency-free runner that executes the same node functions in the
same order/branching that the real LangGraph workflow (workflow.py) uses.

Why this exists: LangGraph itself cannot be installed in the authoring
sandbox for this project (no network access), so this runner is what
lets the actual routing / fan-out-fan-in / retry / escalation logic be
executed and tested for real, rather than only syntax-checked. It is not
a mock of the graph -- it implements the identical state machine:

    router
      -> rag, sql, tools   (independent; LangGraph would run these
                             concurrently, this runs them in sequence,
                             which is observably identical since they
                             only read `classification` and write
                             disjoint keys)
      -> diagnosis
      -> validation
           -> valid                      -> safe_response -> END
           -> invalid, retries remain    -> diagnosis (loop)
           -> invalid, retries exhausted -> human_review -> END
           -> requires_human             -> human_review -> END

``workflow.py`` wires the identical node functions into a real
``StateGraph`` for production/parallel execution.
"""

from __future__ import annotations

from app.graph.deps import GraphDeps
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

MAX_RETRIES = 2


def run_graph(
    user_query: str,
    deps: GraphDeps,
    request_id: str = "test-request",
    user_access_level: str = "standard",
    max_retries: int = MAX_RETRIES,
) -> GraphState:
    state: GraphState = {
        "request_id": request_id,
        "user_query": user_query,
        "user_access_level": user_access_level,
        "retry_count": 0,
        "errors": [],
    }

    state.update(router_node(state, deps))

    # Fan-out (independent branches) then fan-in -- order doesn't matter
    # since each writes a disjoint state key and only reads `classification`.
    state.update(rag_node(state, deps))
    state.update(sql_node(state, deps))
    state.update(tools_node(state, deps))

    for _ in range(max_retries + 1):
        state.update(diagnosis_node(state, deps))
        state.update(validation_node(state, deps))

        validation = state["validation"]
        if validation["requires_human"] and state["diagnosis"].get("requires_human"):
            # High-risk actions escalate immediately, no retry loop.
            state.update(human_review_node(state, deps))
            return state

        if validation["is_valid"]:
            state.update(safe_response_node(state, deps))
            return state

        state["retry_count"] = state.get("retry_count", 0) + 1
        if state["retry_count"] > max_retries:
            state.update(human_review_node(state, deps))
            return state
        # else: loop back to diagnosis (retry), never exceeding max_retries

    # Defensive fallback -- should be unreachable given the loop bounds above.
    state.update(human_review_node(state, deps))
    return state
