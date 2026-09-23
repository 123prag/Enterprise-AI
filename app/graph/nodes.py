"""Graph node functions.

Each node is a plain function ``(state, deps) -> partial_state_update``,
independent of both LangGraph and the concrete tool/RAG implementations
(injected via ``deps`` -- see graph/deps.py). This is what lets
``app/graph/runner.py`` execute and test the full routing/retry/
escalation logic in this sandbox without the langgraph package or the
pydantic/SQLAlchemy-based tools being installed.

Diagnosis and validation here are intentionally minimal placeholders --
Phase 6 replaces them with dedicated ``diagnosis_agent.py`` /
``validation_agent.py`` modules that reason more carefully over the
gathered evidence. The graph *shape* (fan-out to RAG/SQL/tools, fan-in to
diagnosis, validate-or-retry-or-escalate) is final as of this phase.
"""

from __future__ import annotations

from app.agents.orchestrator import classify
from app.graph.deps import GraphDeps
from app.graph.state import GraphState

MAX_RETRIES_DEFAULT = 2
CONFIDENCE_THRESHOLD_DEFAULT = 0.7


def router_node(state: GraphState, deps: GraphDeps) -> dict:
    classification = classify(state["user_query"])
    return {"classification": classification.model_dump()}


def rag_node(state: GraphState, deps: GraphDeps) -> dict:
    classification = state.get("classification", {})
    if not classification.get("requires_rag"):
        return {"retrieved_documents": []}

    result = deps.search_knowledge_base(state["user_query"], None)
    ok = result.get("success", True)
    citations = result.get("citations", []) if ok else []
    new_errors = state.get("errors", [])
    if not ok:
        new_errors = new_errors + [result.get("error", "unknown RAG error")]
    return {"retrieved_documents": citations, "errors": new_errors}


def sql_node(state: GraphState, deps: GraphDeps) -> dict:
    classification = state.get("classification", {})
    if not classification.get("requires_database"):
        return {"incident_results": []}

    category = classification.get("category")
    filters = {"limit": 10}
    if category and category != "General":
        filters["category"] = category

    result = deps.search_incidents(filters)
    ok = result.get("success", True)
    incidents = result.get("incidents", []) if ok else []
    new_errors = state.get("errors", [])
    if not ok:
        new_errors = new_errors + [result.get("error", "unknown SQL error")]
    return {"incident_results": incidents, "errors": new_errors}


def tools_node(state: GraphState, deps: GraphDeps) -> dict:
    classification = state.get("classification", {})
    if not classification.get("requires_tools"):
        return {"tool_results": {}}

    action = classification.get("detected_action")
    tool_results: dict = {}

    if action == "create_ticket":
        tool_results["create_ticket"] = deps.run_tool(
            "create_ticket",
            {
                "title": f"Auto-generated: {state['user_query'][:80]}",
                "description": state["user_query"],
                "created_by": "copilot-system",
            },
        )
    elif action == "check_status":
        tool_results["check_system_status"] = deps.run_tool("check_system_status", {})
    elif classification.get("requires_human"):
        # High-risk actions are never executed here -- only surfaced for
        # human review (Phase 7 formalizes this via human_approvals).
        tool_results["blocked_pending_approval"] = {
            "reason": "High-risk action requires human approval before execution."
        }

    return {"tool_results": tool_results}


def diagnosis_node(state: GraphState, deps: GraphDeps) -> dict:
    """Placeholder diagnosis: combines whatever evidence was gathered into
    a concise summary and a heuristic confidence score. Replaced by a
    dedicated agent in Phase 6.
    """
    classification = state.get("classification", {})
    docs = state.get("retrieved_documents", [])
    incidents = state.get("incident_results", [])

    evidence = []
    if docs:
        evidence.append(f"{len(docs)} relevant document section(s) found.")
    if incidents:
        evidence.append(f"{len(incidents)} historical incident(s) found in the same category.")

    if classification.get("requires_human"):
        diagnosis_text = (
            "This request involves a high-risk action that cannot be diagnosed "
            "or executed automatically and must be reviewed by a human."
        )
        confidence = 0.0
        risk_level = "high"
    elif not evidence:
        diagnosis_text = (
            "No supporting documentation or historical incidents were found "
            "for this query."
        )
        confidence = 0.2
        risk_level = "medium"
    else:
        diagnosis_text = " ".join(evidence) + " See cited sources for details."
        confidence = min(0.5 + 0.2 * len(evidence), 0.95)
        risk_level = "low"

    diagnosis = {
        "diagnosis": diagnosis_text,
        "confidence": confidence,
        "evidence": evidence,
        "recommended_actions": list(state.get("tool_results", {}).keys()),
        "risk_level": risk_level,
        "requires_human": classification.get("requires_human", False),
    }
    return {"diagnosis": diagnosis, "confidence": confidence, "risk_level": risk_level}


def validation_node(state: GraphState, deps: GraphDeps) -> dict:
    """Placeholder validation: checks the diagnosis is evidence-backed and
    above the confidence threshold. Replaced by a dedicated agent (with
    hallucination/citation/policy checks) in Phase 6.
    """
    diagnosis = state.get("diagnosis", {})
    confidence = state.get("confidence", 0.0)
    is_high_risk = diagnosis.get("requires_human", False)

    reasons = []
    is_valid = True

    if is_high_risk:
        is_valid = False
        reasons.append("High-risk action always requires human approval.")
    elif confidence < CONFIDENCE_THRESHOLD_DEFAULT:
        is_valid = False
        reasons.append(
            f"Confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD_DEFAULT}."
        )
    elif not diagnosis.get("evidence"):
        is_valid = False
        reasons.append("Diagnosis is not backed by any retrieved evidence.")

    validation = {
        "is_valid": is_valid,
        "requires_human": is_high_risk or not is_valid,
        "reasons": reasons,
    }
    return {"validation": validation}


def safe_response_node(state: GraphState, deps: GraphDeps) -> dict:
    diagnosis = state.get("diagnosis", {})
    docs = state.get("retrieved_documents", [])
    citation_str = ""
    if docs:
        names = sorted({d.get("document_name", "") for d in docs})
        citation_str = f" (Sources: {', '.join(names)})"

    response = f"{diagnosis.get('diagnosis', '')}{citation_str}"
    return {"final_response": response}


def human_review_node(state: GraphState, deps: GraphDeps) -> dict:
    diagnosis = state.get("diagnosis", {})
    reasons = state.get("validation", {}).get("reasons", [])
    response = (
        "This request has been escalated for human review "
        f"(risk level: {state.get('risk_level', 'unknown')}). "
        f"Reason: {'; '.join(reasons) if reasons else 'policy requires approval.'}"
    )
    human_approval = {
        "proposed_action": state["user_query"],
        "risk_level": state.get("risk_level", "medium"),
        "reason": "; ".join(reasons) or diagnosis.get("diagnosis", ""),
        "decision": "pending",
    }
    return {"final_response": response, "human_approval": human_approval}
