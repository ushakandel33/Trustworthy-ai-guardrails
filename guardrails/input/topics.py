"""Sensitive-topic classification.

Approach: a keyword and phrase classifier. Each category has a list of
patterns; the category with the most matches wins, with ties broken by the
order of CATEGORY_POLICY (most severe first). A policy table maps each category
to an action, so changing how a topic is handled does not touch detection code.

Limitations: keyword matching has no understanding of context. Indirect
wording ("I don't see the point of anything any more") can be missed, and
words like "kill" in "kill a process" can cause false alarms.
"""

from __future__ import annotations

import re

from guardrails.models import GuardrailResult

# Ordered from most to least severe; order is used to break ties.
CATEGORY_POLICY: dict[str, dict[str, str]] = {
    "self_harm": {
        "action": "escalate",
        "message": (
            "I'm really sorry you're feeling this way. You don't have to deal with it alone. "
            "Please call the campus emergency line on extension 100 now, or go to the nearest hospital. "
            "The Student Wellbeing Centre in Block C offers free, confidential counselling."
        ),
    },
    "violence": {
        "action": "block",
        "message": "I can't help with that. If someone is in danger, call the campus emergency line on extension 100.",
    },
    "academic_misconduct": {
        "action": "refuse",
        "message": (
            "I can't help with that because it would break the academic integrity policy. "
            "I can help you with deadlines, extensions or where to find study support."
        ),
    },
    "harassment": {
        "action": "add_disclaimer",
        "message": "If you are experiencing harassment or discrimination, you can report it confidentially to the Registrar's Office or the Student Wellbeing Centre.",
    },
    "medical": {
        "action": "add_disclaimer",
        "message": "This is general information, not medical advice. Please see a qualified health professional about your symptoms.",
    },
    "legal": {
        "action": "add_disclaimer",
        "message": "This is general information, not legal advice. For your specific situation, please talk to a qualified adviser.",
    },
}

TOPIC_PATTERNS: dict[str, list[str]] = {
    "self_harm": [
        r"\b(kill|hurt|harm) (myself|me)\b", r"\bsuicid", r"\bend (my|it all|my life)\b",
        r"\bwant to die\b", r"\bself[- ]harm", r"\bcut(ting)? myself\b", r"\bno reason to live\b",
    ],
    "violence": [
        r"\b(make|build|get)\b.{0,20}\b(bomb|explosive|gun|weapon)", r"\b(attack|shoot|stab|kill)\b.{0,20}\b(teacher|lecturer|student|people|him|her|them)\b",
        r"\bpoison (someone|him|her|them)\b",
    ],
    "academic_misconduct": [
        r"\b(write|do|complete|take)\b.{0,15}\b(my|the)\b.{0,15}\b(exam|assignment|essay|thesis|test) for me\b",
        r"\b(exam|test) (answers|paper) (before|leak)", r"\bleaked (exam|paper|answers)\b",
        r"\b(bypass|avoid|beat|cheat)\b.{0,20}\b(plagiarism|turnitin)\b", r"\bcheat (in|on|during)\b",
    ],
    "harassment": [
        r"\bharass", r"\bbull(y|ied|ying)\b", r"\bdiscriminat", r"\bstalk", r"\bsexual(ly)? (comment|advance|misconduct)",
    ],
    "medical": [
        r"\b(symptom|diagnos|medication|medicine|prescription|dosage|fever|infection|pregnan)", r"\b(sick|ill|illness|injury|injured)\b",
        r"\b(depress|anxiety|panic attack)",
    ],
    "legal": [
        r"\b(sue|lawsuit|lawyer|legal action|court|visa|immigration|contract)\b",
    ],
}

_COMPILED = {c: [re.compile(p, re.IGNORECASE) for p in ps] for c, ps in TOPIC_PATTERNS.items()}


def classify_topic(text: str) -> GuardrailResult:
    counts = {c: sum(1 for p in ps if p.search(text)) for c, ps in _COMPILED.items()}
    matched = {c: n for c, n in counts.items() if n}
    if not matched:
        return GuardrailResult("sensitive_topic", False, "allow", "", {"category": None})
    order = list(CATEGORY_POLICY)
    category = sorted(matched, key=lambda c: (-matched[c], order.index(c)))[0]
    # A self-harm signal always wins: missing it is the most costly error.
    if "self_harm" in matched:
        category = "self_harm"
    policy = CATEGORY_POLICY[category]
    return GuardrailResult(
        "sensitive_topic",
        True,
        policy["action"],
        f"Classified as {category}",
        {"category": category, "all_matches": matched, "message": policy["message"]},
    )
