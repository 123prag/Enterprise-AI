"""Validation Agent.

Checks a diagnosis before it's allowed to reach the user:

- evidence support: a diagnosis claiming a cause must have at least one
  piece of retrieved evidence backing it (citation, incident, or tool
  signal) -- an unsupported claim fails validation regardless of stated
  confidence.
- citation correctness: any "[n]" marker present in the diagnosis text
  must correspond to an actual citation returned by the RAG agent; a
  marker with no matching citation is treated as a hallucinated
  reference and fails validation.
- confidence threshold: below the configured threshold, human review is
  required rather than surfacing a low-confidence answer directly.
- policy compliance: a diagnosis is never allowed to mark a high-risk
  request as auto-resolvable -- classification.requires_human always
  wins regardless of what the diagnosis agent concluded.

A strict retry limit (enforced by the graph, not here) prevents infinite
diagnosis<->validation loops; this agent only ever reports pass/fail plus
reasons, it does not loop itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_MARKER_PATTERN = re.compile(r"\[(\d+)\]")


@dataclass
class ValidationResult:
    is_valid: bool
    requires_human: bool
    reasons: list[str]


def _find_hallucinated_markers(diagnosis_text: str, citation_count: int) -> list[str]:
    referenced = {int(m) for m in CITATION_MARKER_PATTERN.findall(diagnosis_text)}
    valid_range = set(range(1, citation_count + 1))
    return [f"[{n}]" for n in sorted(referenced - valid_range)]


def validate(
    diagnosis: dict,
    classification: dict,
    citation_count: int,
    confidence_threshold: float = 0.7,
) -> ValidationResult:
    reasons: list[str] = []
    is_valid = True

    # Policy compliance overrides everything else: a high-risk classification
    # can never be marked resolvable by the diagnosis agent.
    if classification.get("requires_human") or diagnosis.get("requires_human"):
        return ValidationResult(
            is_valid=False,
            requires_human=True,
            reasons=["Policy requires human approval for this high-risk request."],
        )

    diagnosis_text = diagnosis.get("diagnosis", "")
    evidence = diagnosis.get("evidence", [])
    confidence = diagnosis.get("confidence", 0.0)

    # Evidence support
    if not evidence:
        is_valid = False
        reasons.append("Diagnosis is not backed by any retrieved evidence.")

    # Citation correctness / hallucination check
    hallucinated = _find_hallucinated_markers(diagnosis_text, citation_count)
    if hallucinated:
        is_valid = False
        reasons.append(
            f"Diagnosis references citation marker(s) {hallucinated} that do not "
            f"exist in the {citation_count} retrieved citation(s) -- possible "
            "hallucinated source."
        )

    # Confidence threshold
    if confidence < confidence_threshold:
        is_valid = False
        reasons.append(
            f"Confidence {confidence:.2f} is below the required threshold "
            f"{confidence_threshold:.2f}."
        )

    # Unsafe recommendation check: the diagnosis agent must never recommend
    # directly executing a high-risk action -- only escalation.
    unsafe_actions = {"create_production_change", "delete_account", "suspend_account"}
    recommended = set(diagnosis.get("recommended_actions", []))
    unsafe_hit = recommended & unsafe_actions
    if unsafe_hit:
        is_valid = False
        reasons.append(f"Diagnosis recommends unsafe action(s) without approval: {unsafe_hit}")

    return ValidationResult(
        is_valid=is_valid,
        requires_human=not is_valid,
        reasons=reasons,
    )
