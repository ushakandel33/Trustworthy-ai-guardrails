"""PII detection and redaction.

Approach: regular expressions for structured identifiers, a Luhn checksum for
card numbers (to cut false positives on long numbers), and keyword context for
identifiers that have no fixed format (citizenship, passport, date of birth,
passwords). Overlapping matches are resolved by keeping the longest span.

Action: every match is replaced with a typed placeholder such as [EMAIL]
before the text reaches the model, so the model never sees the raw value.

Limitations: names, street addresses and free-text identifiers are not
detected; numbers spelled out in words or split by unusual characters slip
through; formats from other countries may be missed.
"""

from __future__ import annotations

import re

from guardrails.models import GuardrailResult, Span

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # Nepali mobile numbers (98x / 97x, optional +977) and generic international numbers.
    "PHONE": re.compile(
        r"(?<!\w)(?:\+?977[-\s]?)?9[678]\d{8}\b"
        r"|(?<!\w)\+\d{1,3}[-\s]?\(?\d{1,4}\)?(?:[-\s]?\d{2,4}){2,3}\b"
        r"|(?<!\w)\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
    ),
    "CARD_NUMBER": re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "STUDENT_ID": re.compile(r"\bHIT[-\s]?\d{4}[-\s]?\d{3,4}\b", re.IGNORECASE),
    "NATIONAL_ID": re.compile(
        r"(?i)\b(?:citizenship|passport|national\s+id|pan)\s*(?:no\.?|number|#)?\s*(?:is|:)?\s*([A-Z0-9][A-Z0-9/-]{4,})"
    ),
    "DATE_OF_BIRTH": re.compile(
        r"(?i)\b(?:dob|date\s+of\s+birth|born\s+on)\s*(?:is|:)?\s*(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})"
    ),
    "PASSWORD": re.compile(r"(?i)\b(?:password|passcode|pin)\s*(?:is|:|=)\s*(\S+)"),
    "IP_ADDRESS": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

# Types considered high risk: the user is warned even though the value is redacted.
HIGH_RISK = {"CARD_NUMBER", "SSN", "NATIONAL_ID", "PASSWORD"}


def _luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_pii(text: str, allowlist: set[str] | None = None) -> list[Span]:
    allowlist = {a.lower() for a in (allowlist or set())}
    spans: list[Span] = []
    for kind, pattern in PII_PATTERNS.items():
        for m in pattern.finditer(text):
            # Context patterns capture only the value, not the keyword in front of it.
            start, end = (m.start(1), m.end(1)) if m.groups() and m.group(1) else (m.start(), m.end())
            value = text[start:end]
            if kind == "CARD_NUMBER" and not _luhn_ok(value):
                continue
            if value.lower() in allowlist:
                continue
            spans.append(Span(kind, start, end, value))
    # Resolve overlaps: longest span wins.
    spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
    kept: list[Span] = []
    for s in spans:
        if kept and s.start < kept[-1].end:
            if (s.end - s.start) > (kept[-1].end - kept[-1].start):
                kept[-1] = s
            continue
        kept.append(s)
    return kept


def redact(text: str, spans: list[Span]) -> str:
    out = text
    for s in sorted(spans, key=lambda s: s.start, reverse=True):
        out = out[: s.start] + f"[{s.kind}]" + out[s.end :]
    return out


def check_input_pii(text: str) -> tuple[GuardrailResult, str]:
    """Detect PII in user input and return the result plus the redacted text."""
    spans = find_pii(text)
    if not spans:
        return GuardrailResult("input_pii", False, "allow"), text
    kinds = sorted({s.kind for s in spans})
    high = sorted(set(kinds) & HIGH_RISK)
    reason = f"Redacted {len(spans)} item(s): {', '.join(kinds)}"
    if high:
        reason += f". High-risk data shared ({', '.join(high)}); user is warned."
    return (
        GuardrailResult(
            "input_pii",
            True,
            "redact",
            reason,
            {"types": kinds, "count": len(spans), "high_risk": high},
        ),
        redact(text, spans),
    )
