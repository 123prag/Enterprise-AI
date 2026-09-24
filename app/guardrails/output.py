"""Output guardrails: screen generated responses before they reach the
user.

Catches accidental leakage of secrets/credentials (in case retrieved
context or a tool result ever contained one) and system-prompt/internal-
instruction leakage. This is a last line of defense, not a substitute for
the diagnosis/validation agents' hallucination and citation checks
(Phase 6) -- those catch unsupported claims; this catches leaked
sensitive text regardless of how it got into the response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SECRET_PATTERNS = [
    r"\bsk-[a-zA-Z0-9]{20,}\b",  # OpenAI-style key
    r"\bAKIA[0-9A-Z]{16}\b",  # AWS access key id
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\bpassword\s*[:=]\s*\S+",
    r"\bapi[_-]?key\s*[:=]\s*\S+",
]

SYSTEM_LEAKAGE_PATTERNS = [
    r"\byou are an? (senior|enterprise|helpful) ai\b",  # echoing a system-prompt framing verbatim
    r"\bmy system prompt is\b",
    r"\bas instructed by my system prompt\b",
]


@dataclass
class OutputGuardrailResult:
    is_safe: bool
    violations: list[str] = field(default_factory=list)
    redacted_text: str | None = None


def _redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted


def check_output(text: str) -> OutputGuardrailResult:
    violations: list[str] = []

    if any(re.search(p, text, re.IGNORECASE) for p in SECRET_PATTERNS):
        violations.append("possible_secret_or_credential_in_output")

    if any(re.search(p, text, re.IGNORECASE) for p in SYSTEM_LEAKAGE_PATTERNS):
        violations.append("possible_system_prompt_leakage")

    if not violations:
        return OutputGuardrailResult(is_safe=True)

    return OutputGuardrailResult(
        is_safe=False, violations=violations, redacted_text=_redact(text)
    )
