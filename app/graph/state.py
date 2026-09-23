"""LangGraph state schema.

A single TypedDict flows through every node. Fields are additive per
node (each node returns only the keys it changes; LangGraph merges them
into the running state) — this file is the single source of truth for
what's in that state, referenced by both the real graph (workflow.py)
and the dependency-free runner (runner.py) used for testing without the
langgraph package installed.

No hidden chain-of-thought is stored here — ``diagnosis`` and
``validation`` hold concise, evidence-backed summaries only (see
app/agents/diagnosis_agent.py and validation_agent.py in Phase 6).
"""

from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    # identity / tracing
    request_id: str
    trace_id: str

    # input
    user_query: str
    user_access_level: str

    # routing
    classification: dict[str, Any]

    # evidence gathered by parallel branches
    retrieved_documents: list[dict[str, Any]]
    rag_answer: str
    incident_results: list[dict[str, Any]]
    tool_results: dict[str, Any]

    # reasoning
    diagnosis: dict[str, Any]
    confidence: float
    validation: dict[str, Any]
    risk_level: str

    # control flow
    retry_count: int
    human_approval: dict[str, Any]

    # output
    final_response: str
    errors: list[str]
