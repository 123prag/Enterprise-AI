"""Graph node functions.

Each node is a plain function ``(state, deps) -> partial_state_update``,
independent of both LangGraph and the concrete tool/RAG implementations
(injected via ``deps`` -- see graph/deps.py). This is what lets
``app/graph/runner.py`` execute and test the full routing/retry/
escalation logic in this sandbox without the langgraph package or the
pydantic/SQLAlchemy-based tools being installed.

Diagnosis and validation delegate to the dedicated agents in
``app/agents/diagnosis_agent.py`` and ``app/agents/validation_agent.py``
(Phase 6). The graph *shape* (fan-out to RAG/SQL/tools, fan-in to
diagnosis, validate-or-retry-or-escalate) was finalized in Phase 5 and is
unchanged here.
"""

from __future__ import annotations

from app.agents import diagnosis_agent, validation_agent
from app.agents.orchestrator import classify
from app.graph.deps import GraphDeps
from app.graph.state import GraphState
from app.guardrails.input import check_input
from app.guardrails.output import check_output

MAX_RETRIES_DEFAULT = 2
CONFIDENCE_THRESHOLD_DEFAULT = 0.7

REFUSAL_MESSAGE = (
    "I can't help with that request. It appears to contain an attempt to "
    "override my instructions or access sensitive internal information, "
    "which I'm not able to act on."
)


def guardrail_input_node(state: GraphState, deps: GraphDeps) -> dict:
    result = check_input(state["user_query"])
    if not result.is_safe:
        return {
            "blocked": True,
            "block_reason": "; ".join(result.violations),
            "final_response": REFUSAL_MESSAGE,
        }
    return {"blocked": False, "block_reason": ""}


def guardrail_output_node(state: GraphState, deps: GraphDeps) -> dict:
    text = state.get("final_response", "")
    if not text:
        return {}

    result = check_output(text)
    if result.is_safe:
        return {}

    return {
        "final_response": (
            "[Response withheld: the generated content triggered an output "
            "safety check and has been blocked from display.]"
        ),
        "errors": state.get("errors", []) + result.violations,
    }


def router_node(state: GraphState, deps: GraphDeps) -> dict:
    classification = classify(state["user_query"])
    return {"classification": classification.model_dump()}


def rag_node(state: GraphState, deps: GraphDeps) -> dict:
    classification = state.get("classification", {})
    if not classification.get("requires_rag"):
        return {"retrieved_documents": [], "rag_answer": ""}

    result = deps.search_knowledge_base(state["user_query"], None)
    ok = result.get("success", True)
    citations = result.get("citations", []) if ok else []
    rag_answer = result.get("answer", "") if ok else ""
    new_errors = state.get("errors", [])
    if not ok:
        new_errors = new_errors + [result.get("error", "unknown RAG error")]
    return {"retrieved_documents": citations, "rag_answer": rag_answer, "errors": new_errors}


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
    classification = state.get("classification", {})
    incidents = state.get("incident_results", [])
    citations = state.get("retrieved_documents", [])

    known_problematic = False
    if not classification.get("requires_human"):
        signal = diagnosis_agent.extract_software_signal(
            state["user_query"], classification.get("category", ""), incidents
        )
        if signal:
            product, version = signal
            result = deps.run_tool(
                "check_software_version", {"product_name": product, "version": version}
            )
            known_problematic = bool(result.get("is_known_problematic"))

    result = diagnosis_agent.diagnose(
        user_query=state["user_query"],
        classification=classification,
        rag_answer=state.get("rag_answer", ""),
        citations=citations,
        incidents=incidents,
        tool_results=state.get("tool_results", {}),
        known_problematic_version=known_problematic,
    )

    diagnosis = {
        "diagnosis": result.diagnosis,
        "confidence": result.confidence,
        "evidence": result.evidence,
        "recommended_actions": result.recommended_actions,
        "risk_level": result.risk_level,
        "requires_human": result.requires_human,
    }
    return {"diagnosis": diagnosis, "confidence": result.confidence, "risk_level": result.risk_level}


def validation_node(state: GraphState, deps: GraphDeps) -> dict:
    classification = state.get("classification", {})
    diagnosis = state.get("diagnosis", {})
    citation_count = len(state.get("retrieved_documents", []))

    result = validation_agent.validate(
        diagnosis=diagnosis,
        classification=classification,
        citation_count=citation_count,
        confidence_threshold=CONFIDENCE_THRESHOLD_DEFAULT,
    )
    validation = {
        "is_valid": result.is_valid,
        "requires_human": result.requires_human,
        "reasons": result.reasons,
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
    risk_level = state.get("risk_level", "medium")
    reason_text = "; ".join(reasons) or diagnosis.get("diagnosis", "")

    approval_result = deps.run_tool(
        "request_human_approval",
        {
            "request_id": state.get("request_id", "unknown"),
            "proposed_action": state["user_query"],
            "risk_level": risk_level,
            "reason": reason_text,
        },
    )

    response = (
        "This request has been escalated for human review "
        f"(risk level: {risk_level}). "
        f"Reason: {reason_text or 'policy requires approval.'}"
    )
    human_approval = {
        "approval_id": approval_result.get("approval_id"),
        "proposed_action": state["user_query"],
        "risk_level": risk_level,
        "reason": reason_text,
        "decision": "pending",
        "persisted": approval_result.get("success", False),
    }
    return {"final_response": response, "human_approval": human_approval}
