"""Prompt-injection detection.

Approach: the input is normalised (Unicode NFKC, zero-width characters removed,
common leetspeak undone, whitespace collapsed) and matched against a weighted
pattern bank grouped by attack category. Base64-looking blobs are decoded and
scanned too. Weights add up to a risk score; at or above THRESHOLD the request
is blocked.

Action: block. The model is never called and the user gets a neutral message.

Limitations: patterns only cover phrasings someone has written down, so
paraphrases, other languages and multi-turn set-ups get through. Indirect
injection hidden inside retrieved documents is not scanned. Some benign
sentences ("show me the instructions for ...") look like extraction attempts.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata

from guardrails.models import GuardrailResult

THRESHOLD = 0.6

LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
ZERO_WIDTH = re.compile(r"[​-‏⁠﻿]")

# (category, weight, pattern). Patterns run on normalised lower-case text.
PATTERNS: list[tuple[str, float, re.Pattern[str]]] = [
    # Overriding the instructions the assistant was given.
    ("instruction_override", 0.7, re.compile(r"\b(ignore|disregard|forget|override|skip)\b.{0,30}\b(previous|prior|above|earlier|all|your|system|original)\b.{0,20}\b(instruction|prompt|rule|direction|guideline|polic)")),
    ("instruction_override", 0.6, re.compile(r"\b(new|updated|real) (system )?(instruction|rule|prompt)s?\s*(:|are|is)")),
    ("instruction_override", 0.5, re.compile(r"\bfrom now on,? you (are|will|must|should)\b")),
    # Persona / jailbreak framing.
    ("jailbreak", 0.7, re.compile(r"\b(dan|developer mode|god mode|jailbreak|jailbroken)\b")),
    ("jailbreak", 0.6, re.compile(r"\b(pretend|act|behave|roleplay)\b.{0,30}\b(no|without) (rule|restriction|filter|limit|guideline|ethic)")),
    ("jailbreak", 0.6, re.compile(r"\byou are (now )?(an? )?(unrestricted|unfiltered|uncensored|evil)\b")),
    ("jailbreak", 0.6, re.compile(r"\b(bypass|disable|turn off|remove)\b.{0,20}\b(safety|filter|guardrail|restriction|moderation)")),
    # Extracting the system prompt or configuration.
    ("prompt_extraction", 0.7, re.compile(r"\b(reveal|show|print|output|repeat|display|leak|dump|tell me)\b.{0,30}\b(system prompt|hidden prompt|initial prompt|your instruction|your prompt|your rule|configuration)")),
    ("prompt_extraction", 0.6, re.compile(r"\bwhat (are|were) (your|the) (system |original |hidden )?(instruction|prompt|rule)s?\b")),
    ("prompt_extraction", 0.6, re.compile(r"\b(repeat|print) (everything|all|the text) (above|before)\b")),
    # Asking for confidential data the assistant must not share.
    ("data_exfiltration", 0.7, re.compile(r"\b(list|give|show|export|send|dump)\b.{0,30}\b(all|every|other)\b.{0,20}\b(student|user|staff)s?\b.{0,30}\b(email|phone|record|grade|password|data|detail|address)")),
    ("data_exfiltration", 0.6, re.compile(r"\b(api key|secret key|access token|admin password|database password|credential)s?\b")),
    # Fake role or delimiter markers that try to impersonate the system.
    ("delimiter_injection", 0.6, re.compile(r"(<\s*/?\s*(system|assistant|instruction)s?\s*>|\[/?inst\]|###\s*(system|instruction)|^\s*system\s*:)", re.MULTILINE)),
    # Fake authority.
    ("authority_claim", 0.3, re.compile(r"\b(i am|i'm|this is) (the |an? )?(admin|administrator|developer|system owner|your creator)\b")),
]

B64_BLOB = re.compile(r"\b[A-Za-z0-9+/]{20,}={0,2}")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = ZERO_WIDTH.sub("", text).lower()
    text = text.translate(LEET)
    return re.sub(r"\s+", " ", text)


def _decoded_payloads(text: str) -> list[str]:
    out = []
    for blob in B64_BLOB.findall(text):
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if decoded.isprintable():
            out.append(decoded)
    return out


def score_text(text: str) -> tuple[float, list[dict]]:
    norm = normalise(text)
    hits = []
    for category, weight, pattern in PATTERNS:
        m = pattern.search(norm)
        if m:
            hits.append({"category": category, "weight": weight, "match": m.group(0)[:80]})
    return min(1.0, sum(h["weight"] for h in hits)), hits


def check_injection(text: str) -> GuardrailResult:
    score, hits = score_text(text)
    for payload in _decoded_payloads(text):
        p_score, p_hits = score_text(payload)
        if p_hits:
            hits.extend({**h, "category": "encoded_" + h["category"]} for h in p_hits)
            score = min(1.0, score + p_score)
    flagged = score >= THRESHOLD
    categories = sorted({h["category"] for h in hits})
    return GuardrailResult(
        "prompt_injection",
        flagged,
        "block" if flagged else "allow",
        f"Risk score {score:.2f} ({', '.join(categories)})" if hits else "",
        {"score": round(score, 2), "threshold": THRESHOLD, "hits": hits},
    )
