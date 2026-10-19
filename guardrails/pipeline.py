"""The guarded assistant: input guardrails -> retrieval -> model -> output guardrails."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from guardrails import config
from guardrails.input.injection import check_injection
from guardrails.input.pii import check_input_pii
from guardrails.input.topics import classify_topic
from guardrails.knowledge_base import retrieve
from guardrails.llm import MockLLM
from guardrails.models import GuardrailResult
from guardrails.output.groundedness import check_groundedness
from guardrails.output.schema import validate_schema
from guardrails.output.sensitive_info import check_output_sensitive

MAX_ATTEMPTS = 2  # first try + one retry when the schema check fails


@dataclass
class AssistantReply:
    """What the user gets back, plus a full trace for auditing and tests.

    outcome is one of: answered, blocked, refused, escalated, fallback.
    modifications lists changes made on the way: input_redacted, disclaimer,
    retried, claims_removed, output_redacted.
    """

    text: str
    outcome: str
    modifications: list[str] = field(default_factory=list)
    results: dict[str, GuardrailResult] = field(default_factory=dict)
    references: dict[str, str] = field(default_factory=dict)
    attempts: int = 0

    def flags(self) -> dict[str, bool]:
        return {name: r.flagged for name, r in self.results.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "outcome": self.outcome,
            "modifications": self.modifications,
            "attempts": self.attempts,
            "references": list(self.references),
            "guardrails": {k: v.to_dict() for k, v in self.results.items()},
        }


class GuardedAssistant:
    def __init__(self, llm=None):
        self.llm = llm or MockLLM()

    def handle(self, user_input: str) -> AssistantReply:
        reply = AssistantReply(text="", outcome="answered")
        res = reply.results

        # ---- Input stage: all three checks run so every decision is logged.
        res["input_pii"], clean_input = check_input_pii(user_input)
        res["prompt_injection"] = check_injection(user_input)
        res["sensitive_topic"] = classify_topic(user_input)
        topic = res["sensitive_topic"]

        if res["prompt_injection"].flagged:
            reply.text, reply.outcome = config.BLOCKED_MESSAGE, "blocked"
            return reply
        if topic.action in ("escalate", "block", "refuse"):
            reply.text = topic.details["message"]
            reply.outcome = {"escalate": "escalated", "block": "blocked", "refuse": "refused"}[topic.action]
            return reply

        notices: list[str] = []
        if res["input_pii"].flagged:
            reply.modifications.append("input_redacted")
            notices.append(config.HIGH_RISK_PII_NOTICE if res["input_pii"].details["high_risk"] else config.PII_NOTICE)

        # ---- Model stage: retrieval + generation, retried once on schema failure.
        reply.references = retrieve(clean_input)
        parsed = None
        first_failure: GuardrailResult | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            reply.attempts = attempt
            raw = self.llm.generate(config.SYSTEM_PROMPT, clean_input, reply.references, strict=attempt > 1)
            res["schema"], parsed = validate_schema(raw, set(reply.references))
            if parsed is not None:
                break
            first_failure = first_failure or res["schema"]
            if attempt == 1:
                reply.modifications.append("retried")
        if parsed is None:
            res["schema"].action = "fallback"
            return self._fallback(reply)
        if first_failure:
            # Keep the evidence that the first attempt failed and was retried.
            res["schema"] = first_failure

        # ---- Output stage. Sensitive-information check runs on the full answer
        # first so a leak is caught even if the leaking sentence is later trimmed.
        answer = parsed.answer
        res["output_sensitive"], _ = check_output_sensitive(answer)
        if res["output_sensitive"].action == "fallback":
            return self._fallback(reply)

        cited = {k: v for k, v in reply.references.items() if k in parsed.sources} or reply.references
        res["groundedness"], answer = check_groundedness(answer, cited)
        if res["groundedness"].action == "fallback":
            return self._fallback(reply)
        if res["groundedness"].action == "remove_claims":
            reply.modifications.append("claims_removed")
            notices.append(config.TRIMMED_NOTICE)

        final_check, answer = check_output_sensitive(answer)
        if final_check.flagged:
            reply.modifications.append("output_redacted")

        if topic.action == "add_disclaimer":
            reply.modifications.append("disclaimer")
            notices.append(topic.details["message"])

        reply.text = " ".join([answer, *notices]).strip()
        return reply

    @staticmethod
    def _fallback(reply: AssistantReply) -> AssistantReply:
        reply.text, reply.outcome = config.FALLBACK_MESSAGE, "fallback"
        return reply
