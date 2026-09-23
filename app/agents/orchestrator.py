"""Orchestrator / Router agent.

Classifies the incoming user query into a structured routing decision:
category, priority, and which downstream branches (RAG / SQL / tools /
human) the graph should engage.

This is deliberately a transparent, rule-based classifier rather than an
LLM call: routing decisions gate which agents run and whether an action
requires human approval, so they need to be deterministic, auditable, and
testable without depending on model behavior. (The diagnosis agent in
Phase 6, which reasons over retrieved evidence rather than gating
control flow, is where LLM judgment is actually load-bearing.)
"""

from __future__ import annotations

import re

from pydantic import BaseModel

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "VPN": ["vpn", "691", "619", "800", "809"],
    "Authentication": ["login", "password", "sso", "auth", "mfa", "account access", "locked out"],
    "Network": ["wifi", "wi-fi", "dns", "packet loss", "voip", "network"],
    "Endpoint Security": ["edr", "antivirus", "quarantine", "encryption", "endpoint", "malware"],
    "Software": ["crash", "update", "license", "installation", "application"],
}

HIGH_RISK_PATTERNS = [
    r"\bproduction\b.*\b(config|configuration|change|change)\b",
    r"\bchange\b.*\bproduction\b",
    r"\bsuspend\b.*\baccount\b",
    r"\bdelete\b.*\baccount\b",
    r"\bdisable\b.*\baccount\b",
    r"\bfirewall\b.*\b(change|rule|modify)\b",
    r"\brevoke\b.*\bcredential\b",
    r"\bisolate\b.*\bdevice\b",
]

HISTORY_PATTERNS = [
    r"\bbefore\b",
    r"\bhistory\b",
    r"\bhappened\b",
    r"\bsimilar\b",
    r"\bhow many\b",
    r"\bprevious(ly)?\b",
    r"\brecurr(ing|ence)\b",
    r"\bincidents?\b",
]

ACTION_PATTERNS = {
    "create_ticket": [r"\bcreate\b.*\bticket\b", r"\bopen\b.*\bticket\b", r"\blog\b.*\bticket\b"],
    "check_status": [r"\bstatus\b", r"\bis .* (down|up|working)\b"],
    "check_version": [r"\bversion\b"],
}

DOC_LOOKUP_PATTERNS = [
    r"\bofficial\b",
    r"\bprocedure\b",
    r"\bpolicy\b",
    r"\bsop\b",
    r"\bhow (do|should) i\b",
    r"\btroubleshoot",
    r"\bguide\b",
    r"\bwhat should i do\b",
    r"\bdidn't work\b",
    r"\bdid not work\b",
    r"\bsolution\b",
]


class Classification(BaseModel):
    category: str
    priority: str
    requires_rag: bool
    requires_database: bool
    requires_tools: bool
    requires_human: bool
    detected_action: str | None = None
    reasoning: str


def _detect_category(query_lower: str) -> tuple[str, list[str]]:
    scores = {
        cat: [kw for kw in kws if kw in query_lower] for cat, kws in CATEGORY_KEYWORDS.items()
    }
    best = max(scores, key=lambda c: len(scores[c]))
    if scores[best]:
        return best, scores[best]
    return "General", []


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _detect_action(query_lower: str, suppress_analytics_actions: bool) -> str | None:
    for action, patterns in ACTION_PATTERNS.items():
        if suppress_analytics_actions and action == "check_version":
            # "how many incidents after version X" is an analytics/SQL
            # question, not a request to check the current live version.
            continue
        if _matches_any(patterns, query_lower):
            return action
    return None


def classify(query: str) -> Classification:
    q = query.lower().strip()

    category, matched_terms = _detect_category(q)
    is_high_risk = _matches_any(HIGH_RISK_PATTERNS, q)
    has_error_code = any(term.isdigit() for term in matched_terms)
    wants_history = _matches_any(HISTORY_PATTERNS, q) or has_error_code
    wants_docs = _matches_any(DOC_LOOKUP_PATTERNS, q) or category != "General"
    action = _detect_action(q, suppress_analytics_actions=wants_history)

    requires_human = is_high_risk
    requires_tools = action is not None or is_high_risk
    requires_database = wants_history or is_high_risk
    # A pure "create a ticket for this" follow-up doesn't need fresh doc
    # lookup; everything else diagnostic benefits from checking docs.
    requires_rag = wants_docs and action != "create_ticket"

    if is_high_risk:
        priority = "critical"
    elif category in ("VPN", "Authentication") and wants_history:
        priority = "medium"
    elif category == "General" and action is None:
        priority = "low"
    else:
        priority = "medium"

    reasons = [f"category={category}"]
    if is_high_risk:
        reasons.append("matched high-risk action pattern -> requires_human=True")
    if wants_history:
        reasons.append("matched history/frequency pattern -> requires_database=True")
    if action:
        reasons.append(f"detected action intent {action!r} -> requires_tools=True")
    if requires_rag:
        reasons.append("diagnostic/documentation query -> requires_rag=True")

    return Classification(
        category=category,
        priority=priority,
        requires_rag=requires_rag,
        requires_database=requires_database,
        requires_tools=requires_tools,
        requires_human=requires_human,
        detected_action=action,
        reasoning="; ".join(reasons),
    )
