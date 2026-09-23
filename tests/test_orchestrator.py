"""Phase 5 tests: the rule-based orchestrator/router classifier, checked
against every sample query listed in the project spec.
"""

from app.agents.orchestrator import classify


def test_vpn_error_report_requires_rag_and_database_not_human():
    c = classify("My VPN gives error 691.")
    assert c.category == "VPN"
    assert c.requires_rag is True
    assert c.requires_database is True  # specific error code -> check history
    assert c.requires_human is False


def test_history_followup_requires_database():
    c = classify("Have we seen similar incidents before?")
    assert c.requires_database is True


def test_analytics_question_does_not_trigger_check_version_tool():
    c = classify("How many VPN incidents occurred after version 24H2?")
    assert c.category == "VPN"
    assert c.requires_database is True
    assert c.detected_action is None  # analytics, not a live version check
    assert c.requires_tools is False


def test_procedure_lookup_requires_rag():
    c = classify("What is the official VPN troubleshooting procedure?")
    assert c.requires_rag is True


def test_increasing_incidents_question_requires_rag_and_database():
    c = classify("Why are incidents increasing after the latest update?")
    assert c.requires_database is True


def test_create_ticket_request_detected_as_action():
    c = classify("Create a support ticket for this problem.")
    assert c.detected_action == "create_ticket"
    assert c.requires_tools is True
    assert c.requires_rag is False


def test_find_similar_incidents_requires_database():
    c = classify("Find similar incidents from the last 30 days.")
    assert c.requires_database is True


def test_failed_solution_followup_requires_rag():
    c = classify("The documented solution didn't work. What should I do?")
    assert c.requires_rag is True


def test_production_config_change_requires_human_approval():
    """This is the one hard requirement called out explicitly in the spec:
    a request to change production configuration MUST require human
    approval and must be flagged critical priority."""
    c = classify("Change the production VPN configuration.")
    assert c.requires_human is True
    assert c.priority == "critical"


def test_other_high_risk_patterns_also_require_human():
    for query in [
        "Please suspend this user's account immediately.",
        "Delete the account for former-employee@corp.com.",
        "Modify the firewall rule to allow port 8080.",
        "Revoke the credential for this service account.",
    ]:
        c = classify(query)
        assert c.requires_human is True, f"expected requires_human for: {query!r}"


def test_benign_query_does_not_require_human():
    c = classify("What's the weather like today?")
    assert c.requires_human is False
