"""Phase 5 tests: the full orchestration state machine (router -> fan-out
RAG/SQL/tools -> diagnosis -> validation -> safe_response/retry/human_review),
run via the dependency-free runner with fake GraphDeps.

This exercises the actual routing/retry/escalation logic end to end --
not a mock of it -- since app/graph/runner.py uses the same node functions
that app/graph/workflow.py wires into the real LangGraph StateGraph.
"""

from app.graph.deps import GraphDeps
from app.graph.runner import run_graph


def _deps(kb_citations=None, incidents=None, tool_success=True, known_problematic_version=False):
    def search_kb(query, department):
        return {"success": True, "citations": kb_citations or [], "answer": "Synthesized answer text."}

    def search_incidents(filters):
        return {"success": True, "incidents": incidents or []}

    def run_tool(name, data):
        if not tool_success:
            return {"success": False, "error": "simulated tool failure"}
        if name == "create_ticket":
            return {"success": True, "ticket_ref": "TCK-999999"}
        if name == "check_software_version":
            return {"success": True, "is_known_problematic": known_problematic_version}
        return {"success": True}

    return GraphDeps(
        search_knowledge_base=search_kb,
        search_incidents=search_incidents,
        run_tool=run_tool,
    )


def test_strong_evidence_reaches_safe_response_without_escalation():
    deps = _deps(
        kb_citations=[{"document_name": "VPN Error Code Reference"}, {"document_name": "VPN SOP"}],
        incidents=[
            {"incident_ref": "INC-1", "software_version": "4.12.1"},
            {"incident_ref": "INC-2", "software_version": "4.12.1"},
        ],
        known_problematic_version=True,
    )
    state = run_graph("My VPN gives error 691, has this happened before?", deps)

    assert state["confidence"] >= 0.7
    assert state["validation"]["is_valid"] is True
    assert "human_approval" not in state
    assert state["final_response"]
    assert state["retry_count"] == 0
    # the known-bad-version cross-reference should show up in the evidence trail
    assert any("known-problematic" in e for e in state["diagnosis"]["evidence"])


def test_no_evidence_retries_then_escalates_to_human():
    deps = _deps(kb_citations=[], incidents=[])
    state = run_graph("Why is my toaster making a weird noise?", deps, max_retries=2)

    assert state["retry_count"] > 0
    assert state["retry_count"] <= 3  # bounded by max_retries + 1 diagnosis attempts
    assert "human_approval" in state
    assert state["human_approval"]["decision"] == "pending"


def test_high_risk_action_escalates_immediately_without_retry():
    deps = _deps(
        kb_citations=[{"document_name": "Remote Access Policy"}],
        incidents=[{"incident_ref": "INC-1"}],
    )
    state = run_graph("Change the production VPN configuration.", deps)

    assert state["classification"]["requires_human"] is True
    assert "human_approval" in state
    assert state["retry_count"] == 0  # no retry loop for high-risk actions
    assert "blocked_pending_approval" in state["tool_results"]
    # the risky action itself must never have been executed as a real tool call
    assert "create_ticket" not in state["tool_results"]


def test_create_ticket_action_runs_tool_and_skips_rag():
    deps = _deps()
    state = run_graph("Create a support ticket for this problem.", deps)

    assert state["classification"]["detected_action"] == "create_ticket"
    assert "create_ticket" in state["tool_results"]
    assert state["tool_results"]["create_ticket"]["success"] is True
    assert state["retrieved_documents"] == []  # rag skipped for pure ticket creation


def test_retry_count_never_exceeds_max_retries_before_escalating():
    deps = _deps(kb_citations=[], incidents=[])
    for max_retries in (0, 1, 3):
        state = run_graph("Unanswerable nonsense query xyz", deps, max_retries=max_retries)
        assert state["retry_count"] <= max_retries + 1
        assert "human_approval" in state


def test_tool_failure_is_recorded_but_does_not_crash_the_graph():
    deps = _deps(tool_success=False)
    state = run_graph("Create a support ticket for this problem.", deps)
    assert state["tool_results"]["create_ticket"]["success"] is False
    assert state["final_response"] or "human_approval" in state
