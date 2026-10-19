"""Groundedness validation.

Approach: the answer is split into sentences, and each sentence that makes a
claim is compared with every sentence of the cited reference documents (or of
all retrieved documents when nothing is cited). A claim is supported when

  1. at least SUPPORT_THRESHOLD of its content words appear in one source
     sentence, and
  2. every number in it (times, amounts, percentages, days) appears in the
     reference text.

The numeric check catches the most common hallucination in this domain:
the right sentence with the wrong figure.

Action: if some claims are supported, the unsupported sentences are removed
and the user is told the answer was trimmed. If no claim is supported, the
response is replaced with a safe fallback.

Limitations: lexical overlap is not meaning. A sentence that reuses the
source's words but flips the meaning (for example by adding or dropping "not")
can pass, and a correct paraphrase with different words can be rejected.
"""

from __future__ import annotations

import re

from guardrails.knowledge_base import split_sentences, tokenize
from guardrails.models import GuardrailResult

SUPPORT_THRESHOLD = 0.6
NUMBER = re.compile(r"\d+(?:[:.]\d+)?")

# Sentences that are the assistant's own framing rather than factual claims.
NON_CLAIM = re.compile(
    r"(?i)^(i (could not|couldn't|can't|cannot) find|i don't have|please (contact|ask|check|see)|"
    r"let me know|hope this helps|is there anything)"
)


def _claim_support(claim: str, source_sentences: list[str], source_numbers: set[str]) -> dict:
    claim_tokens = set(tokenize(claim))
    best, best_src = 0.0, ""
    for src in source_sentences:
        src_tokens = set(tokenize(src))
        if not claim_tokens:
            break
        overlap = len(claim_tokens & src_tokens) / len(claim_tokens)
        if overlap > best:
            best, best_src = overlap, src
    missing_numbers = sorted(set(NUMBER.findall(claim)) - source_numbers)
    supported = best >= SUPPORT_THRESHOLD and not missing_numbers
    return {
        "claim": claim,
        "overlap": round(best, 2),
        "missing_numbers": missing_numbers,
        "best_source": best_src,
        "supported": supported,
    }


def check_groundedness(answer: str, references: dict[str, str]) -> tuple[GuardrailResult, str]:
    """Return the result and the answer with unsupported claims removed."""
    source_text = " ".join(references.values())
    source_sentences = split_sentences(source_text)
    source_numbers = set(NUMBER.findall(source_text))

    claims = []
    for sentence in split_sentences(answer):
        if NON_CLAIM.search(sentence) or len(tokenize(sentence)) < 3:
            continue
        claims.append(_claim_support(sentence, source_sentences, source_numbers))

    unsupported = [c for c in claims if not c["supported"]]
    details = {"claims": claims, "supported": len(claims) - len(unsupported), "total": len(claims)}
    if not unsupported:
        return GuardrailResult("groundedness", False, "allow", "", details), answer

    kept = answer
    for c in unsupported:
        kept = kept.replace(c["claim"], "").strip()
    kept = re.sub(r"\s{2,}", " ", kept)
    if len(unsupported) == len(claims):
        action, reason = "fallback", f"No claims supported by the reference documents (0/{len(claims)})"
    else:
        action = "remove_claims"
        reason = f"Removed {len(unsupported)} unsupported claim(s) of {len(claims)}"
    return GuardrailResult("groundedness", True, action, reason, details), kept
