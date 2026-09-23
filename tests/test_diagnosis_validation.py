"""Phase 6 tests: diagnosis and validation agents, tested directly (these
modules depend only on the standard library, so no shim is needed here).
"""

from app.agents.diagnosis_agent import diagnose, extract_software_signal
from app.agents.validation_agent import validate

# --------------------------------------------------------------------------
# diagnosis_agent
# --------------------------------------------------------------------------


def test_high_risk_classification_short_circuits_to_zero_confidence():
    result = diagnose(
        user_query="Change the production VPN configuration.",
        classification={"requires_human": True},
        rag_answer="",
        citations=[],
        incidents=[],
        tool_results={},
    )
    assert result.confidence == 0.0
    assert result.requires_human is True
    assert result.risk_level == "high"
    assert result.recommended_actions == ["escalate_to_human"]


def test_no_evidence_yields_low_confidence_and_says_so():
    result = diagnose(
        user_query="Why is my toaster making a weird noise?",
        classification={"requires_human": False, "category": "General"},
        rag_answer="",
        citations=[],
        incidents=[],
        tool_results={},
    )
    assert result.confidence < 0.3
    assert "No supporting" in result.diagnosis
    assert result.evidence == []


def test_confidence_increases_with_each_evidence_source():
    base = diagnose(
        "q", {"requires_human": False, "category": "VPN"}, "", [], [], {}
    )
    with_citations = diagnose(
        "q",
        {"requires_human": False, "category": "VPN"},
        "",
        [{"document_name": "Doc A"}],
        [],
        {},
    )
    with_citations_and_incidents = diagnose(
        "q",
        {"requires_human": False, "category": "VPN"},
        "",
        [{"document_name": "Doc A"}],
        [{"incident_ref": "INC-1"}],
        {},
    )
    with_known_bad_version = diagnose(
        "q",
        {"requires_human": False, "category": "VPN"},
        "",
        [{"document_name": "Doc A"}],
        [{"incident_ref": "INC-1"}],
        {},
        known_problematic_version=True,
    )
    assert base.confidence < with_citations.confidence < with_citations_and_incidents.confidence
    assert with_known_bad_version.confidence > with_citations_and_incidents.confidence


def test_rag_answer_used_verbatim_when_evidence_present():
    result = diagnose(
        "q",
        {"requires_human": False, "category": "VPN"},
        rag_answer="The VPN client has a known credential cache bug.",
        citations=[{"document_name": "VPN Error Code Reference"}],
        incidents=[],
        tool_results={},
    )
    assert result.diagnosis == "The VPN client has a known credential cache bug."


def test_extract_software_signal_from_explicit_version_in_query():
    signal = extract_software_signal(
        "My VPN gives error 691 after upgrading to Windows 24H2", "VPN", []
    )
    assert signal == ("CorpVPN Client", "24H2")


def test_extract_software_signal_falls_back_to_incident_history():
    signal = extract_software_signal(
        "My VPN keeps disconnecting",
        "VPN",
        [{"software_version": "4.12.1"}, {"software_version": "4.12.1"}, {"software_version": "5.0.0"}],
    )
    assert signal == ("CorpVPN Client", "4.12.1")  # most common


def test_extract_software_signal_none_for_unmapped_category():
    assert extract_software_signal("some query", "General", []) is None


# --------------------------------------------------------------------------
# validation_agent
# --------------------------------------------------------------------------


def test_validation_passes_well_supported_high_confidence_diagnosis():
    diagnosis = {
        "diagnosis": "See [1] for details.",
        "confidence": 0.9,
        "evidence": ["1 relevant documentation section(s): Doc A"],
        "recommended_actions": [],
        "requires_human": False,
    }
    result = validate(diagnosis, {"requires_human": False}, citation_count=1)
    assert result.is_valid is True
    assert result.requires_human is False
    assert result.reasons == []


def test_validation_fails_on_unsupported_claim():
    diagnosis = {
        "diagnosis": "This is definitely a firmware bug.",
        "confidence": 0.9,
        "evidence": [],
        "recommended_actions": [],
        "requires_human": False,
    }
    result = validate(diagnosis, {"requires_human": False}, citation_count=0)
    assert result.is_valid is False
    assert any("not backed by any retrieved evidence" in r for r in result.reasons)


def test_validation_fails_on_hallucinated_citation_marker():
    diagnosis = {
        "diagnosis": "According to [1] and [3], this is a known issue.",
        "confidence": 0.9,
        "evidence": ["1 relevant documentation section(s): Doc A"],
        "recommended_actions": [],
        "requires_human": False,
    }
    # only 1 citation actually exists, but the diagnosis references [3] too
    result = validate(diagnosis, {"requires_human": False}, citation_count=1)
    assert result.is_valid is False
    assert any("[3]" in r for r in result.reasons)


def test_validation_fails_below_confidence_threshold():
    diagnosis = {
        "diagnosis": "See [1].",
        "confidence": 0.4,
        "evidence": ["1 relevant documentation section(s): Doc A"],
        "recommended_actions": [],
        "requires_human": False,
    }
    result = validate(diagnosis, {"requires_human": False}, citation_count=1, confidence_threshold=0.7)
    assert result.is_valid is False
    assert any("below the required threshold" in r for r in result.reasons)


def test_validation_always_requires_human_for_high_risk_classification():
    """Even a supremely confident, well-evidenced diagnosis must be
    overridden by policy if the classification itself is high-risk."""
    diagnosis = {
        "diagnosis": "Everything checks out.",
        "confidence": 0.99,
        "evidence": ["overwhelming evidence"],
        "recommended_actions": [],
        "requires_human": False,
    }
    result = validate(diagnosis, {"requires_human": True}, citation_count=5)
    assert result.is_valid is False
    assert result.requires_human is True


def test_validation_fails_on_unsafe_recommended_action():
    diagnosis = {
        "diagnosis": "See [1].",
        "confidence": 0.9,
        "evidence": ["1 relevant documentation section(s): Doc A"],
        "recommended_actions": ["suspend_account"],
        "requires_human": False,
    }
    result = validate(diagnosis, {"requires_human": False}, citation_count=1)
    assert result.is_valid is False
    assert any("unsafe action" in r for r in result.reasons)
