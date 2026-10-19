"""Sensitive-information detection on model output.

Approach: the same PII detector used on input (with an allowlist of public
institutional contacts), plus checks for secrets (API keys, tokens, private
keys), the canary token planted in the system prompt, and internal-only
markers.

Action: PII is redacted and the response is still delivered. A secret, the
canary token or an internal marker means the model leaked something it must
never disclose, so the whole response is blocked and replaced with a fallback.

Limitations: only finds what the patterns describe. Private facts written as
plain prose ("Ram failed his exam") are not PII by pattern and pass through.
"""

from __future__ import annotations

import re

from guardrails.config import CANARY_TOKEN
from guardrails.input.pii import find_pii, redact
from guardrails.knowledge_base import PUBLIC_CONTACTS
from guardrails.models import GuardrailResult

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "API_KEY": re.compile(r"\b(sk|pk|rk)[-_][A-Za-z0-9_-]{16,}\b"),
    "AWS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "PRIVATE_KEY": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "BEARER_TOKEN": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"),
    "INTERNAL_MARKER": re.compile(r"(?i)\b(internal only|confidential - do not share|system prompt:)"),
}


def check_output_sensitive(text: str) -> tuple[GuardrailResult, str]:
    leaks = [k for k, p in SECRET_PATTERNS.items() if p.search(text)]
    if CANARY_TOKEN in text:
        leaks.append("CANARY_TOKEN")
    if leaks:
        return (
            GuardrailResult("output_sensitive", True, "fallback", f"Response leaked {', '.join(leaks)}", {"leaks": leaks}),
            text,
        )
    spans = find_pii(text, allowlist=PUBLIC_CONTACTS)
    if spans:
        kinds = sorted({s.kind for s in spans})
        return (
            GuardrailResult("output_sensitive", True, "redact", f"Redacted {', '.join(kinds)} from response", {"types": kinds}),
            redact(text, spans),
        )
    return GuardrailResult("output_sensitive", False, "allow"), text
