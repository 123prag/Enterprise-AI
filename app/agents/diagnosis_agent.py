"""Diagnosis Agent.

Combines RAG evidence (retrieved doc citations + the RAG pipeline's own
synthesized answer), historical incidents from the SQL agent, and tool
results (e.g. a known-problematic-version confirmation) into a single
structured diagnosis:

    {diagnosis, confidence, evidence, recommended_actions, risk_level,
     requires_human}

No hidden chain-of-thought is produced or stored -- only the concise,
evidence-backed summary above. Confidence is a deterministic function of
how much corroborating evidence was actually found, not a model's
self-reported certainty, so it can't be inflated by fluent-sounding text
with no backing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Mirrors the two known-bad pairings seeded in Phase 2 -- used only as a
# lightweight signal for *which* product/version to ask check_software_version
# about; the actual "is this problematic" answer always comes from the tool
# call (deps.run_tool), never hardcoded here.
_CATEGORY_TO_PRODUCT = {
    "VPN": "CorpVPN Client",
}
_VERSION_PATTERN = re.compile(r"\b(\d+H\d{1,2}|\d+\.\d+(?:\.\d+)?)\b", re.IGNORECASE)


@dataclass
class DiagnosisResult:
    diagnosis: str
    confidence: float
    evidence: list[str]
    recommended_actions: list[str]
    risk_level: str
    requires_human: bool


def extract_software_signal(
    query: str, category: str, incidents: list[dict]
) -> tuple[str, str] | None:
    """Best-effort (product_name, version) guess to check against the
    software_versions table, from an explicit version mention in the query
    or the most common software_version among retrieved incidents."""
    product = _CATEGORY_TO_PRODUCT.get(category)

    match = _VERSION_PATTERN.search(query)
    if match and product:
        return product, match.group(1)

    if product:
        versions = [i.get("software_version") for i in incidents if i.get("software_version")]
        if versions:
            most_common = max(set(versions), key=versions.count)
            return product, most_common

    return None


def diagnose(
    user_query: str,
    classification: dict,
    rag_answer: str,
    citations: list[dict],
    incidents: list[dict],
    tool_results: dict,
    known_problematic_version: bool = False,
) -> DiagnosisResult:
    if classification.get("requires_human"):
        return DiagnosisResult(
            diagnosis=(
                "This request involves a high-risk action that cannot be "
                "diagnosed or executed automatically and must be reviewed "
                "by a human."
            ),
            confidence=0.0,
            evidence=[],
            recommended_actions=["escalate_to_human"],
            risk_level="high",
            requires_human=True,
        )

    evidence: list[str] = []
    confidence = 0.15  # base: some routing happened, but nothing confirmed yet

    if citations:
        evidence.append(
            f"{len(citations)} relevant documentation section(s): "
            + ", ".join(sorted({c.get("document_name", "") for c in citations}))
        )
        confidence += 0.30

    if incidents:
        evidence.append(f"{len(incidents)} historical incident(s) in the same category.")
        confidence += 0.20

    if known_problematic_version:
        evidence.append(
            "The affected software version matches a known-problematic "
            "version on record."
        )
        confidence += 0.25

    if tool_results.get("check_system_status", {}).get("success"):
        services = tool_results["check_system_status"].get("services", [])
        degraded = [s for s in services if s.get("status") != "operational"]
        if degraded:
            names = ", ".join(s["service_name"] for s in degraded)
            evidence.append(f"Live system status shows degraded service(s): {names}.")
            confidence += 0.15

    confidence = min(confidence, 0.97)

    if not evidence:
        diagnosis_text = (
            "No supporting documentation, historical incidents, or system "
            "status signals were found for this query. A confident "
            "diagnosis cannot be made from available evidence."
        )
        risk_level = "medium"
    else:
        # Prefer the RAG pipeline's own synthesized answer (already
        # grounded in retrieved chunk text) when available; otherwise fall
        # back to a plain evidence summary.
        diagnosis_text = rag_answer.strip() if rag_answer and rag_answer.strip() else " ".join(evidence)
        risk_level = "low" if confidence >= 0.7 else "medium"

    recommended_actions = list(tool_results.keys()) or (
        ["search_knowledge_base_for_alternatives"] if not evidence else []
    )

    return DiagnosisResult(
        diagnosis=diagnosis_text,
        confidence=round(confidence, 3),
        evidence=evidence,
        recommended_actions=recommended_actions,
        risk_level=risk_level,
        requires_human=False,
    )
