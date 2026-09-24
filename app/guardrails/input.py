"""Input guardrails: screen the user's query before it reaches the
orchestrator.

Catches prompt injection, jailbreak attempts, and requests for sensitive
system internals (secrets, credentials, the system prompt itself). This
is a pattern-level, auditable check -- the same design choice as the
router classifier in Phase 5: control-flow decisions (block vs. proceed)
need to be deterministic and inspectable, not left to a model's judgment
call about whether it's being attacked.

At the pattern level only: this file stays at the level of *named
behaviors* (e.g. "asks the model to ignore its instructions"), not a
comprehensive annotated phrase catalog -- a catalog like that is exactly
as useful to someone probing for gaps as it is to a defender.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

INJECTION_PATTERNS = [
    r"\bignore (all |any )?(previous|prior|above|earlier) instructions\b",
    r"\bdisregard (your |the )?(previous|prior|system) instructions\b",
    r"\byou are now\b.*\b(dan|jailbroken|unrestricted|free)\b",
    r"\bact as (if you (are|were)|an? )(unrestricted|unfiltered|jailbroken)\b",
    r"\bpretend (you have|to have) no (restrictions|rules|guidelines)\b",
    r"\bnew system prompt\b",
    r"\boverride your (guidelines|instructions|rules|programming)\b",
    r"\bdo anything now\b",
    r"\benter (developer|debug|maintenance) mode\b",
]

SENSITIVE_SYSTEM_REQUEST_PATTERNS = [
    r"\b(reveal|show|print|repeat|output)\b.*\b(system prompt|your instructions|your rules)\b",
    r"\bwhat( is|'s)?\s*your\s*system\s*prompt\b",
    r"\b(api|secret|private)\s*key\b",
    r"\bdatabase (password|credentials)\b",
    r"\benvironment variables?\b.*\b(value|contents?|secret)\b",
]

SQL_INJECTION_HINT_PATTERNS = [
    r";\s*drop\s+table",
    r"--\s*$",
    r"\bunion\s+select\b",
    r"'\s*or\s+'1'\s*=\s*'1",
]


@dataclass
class InputGuardrailResult:
    is_safe: bool
    violations: list[str] = field(default_factory=list)


def _scan(patterns: list[str], text: str, label: str) -> list[str]:
    hits = []
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            hits.append(label)
            break
    return hits


def check_input(query: str) -> InputGuardrailResult:
    violations: list[str] = []
    violations += _scan(INJECTION_PATTERNS, query, "prompt_injection_or_jailbreak_attempt")
    violations += _scan(
        SENSITIVE_SYSTEM_REQUEST_PATTERNS, query, "request_for_system_internals_or_secrets"
    )
    violations += _scan(SQL_INJECTION_HINT_PATTERNS, query, "sql_injection_pattern")

    return InputGuardrailResult(is_safe=not violations, violations=violations)
