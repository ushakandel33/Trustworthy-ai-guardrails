"""Shared result types used by every guardrail."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    """A piece of detected text inside a larger string."""

    kind: str
    start: int
    end: int
    text: str


@dataclass
class GuardrailResult:
    """The outcome of running one guardrail.

    flagged  -- True when the guardrail found something.
    action   -- what the pipeline should do: allow, redact, block, refuse,
                escalate, add_disclaimer, retry, remove_claims, fallback.
    details  -- guardrail-specific evidence (matched patterns, scores, ...).
    """

    name: str
    flagged: bool
    action: str = "allow"
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "flagged": self.flagged,
            "action": self.action,
            "reason": self.reason,
            "details": self.details,
        }
