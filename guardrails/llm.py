"""Language-model back ends.

MockLLM      -- deterministic, extractive; answers by copying the most relevant
                reference sentences. Used for the demo and the evaluation so
                results are reproducible and need no API key.
ScriptedLLM  -- returns pre-written raw outputs in order. The test suite uses it
                to feed the output guardrails bad responses (broken JSON,
                hallucinated figures, leaked data) that a real model produces
                only occasionally.
AnthropicLLM -- optional real model, used when ANTHROPIC_API_KEY is set and
                the `anthropic` package is installed.
"""

from __future__ import annotations

import json
import os

from guardrails.knowledge_base import split_sentences, tokenize


class MockLLM:
    name = "mock"

    def generate(self, system: str, question: str, references: dict[str, str], strict: bool = False) -> str:
        if not references:
            return json.dumps({
                "answer": "I could not find this in the student handbook.",
                "sources": [],
                "confidence": 0.2,
                "status": "not_found",
            })
        q = set(tokenize(question))
        scored = []
        for doc_id, text in references.items():
            for sentence in split_sentences(text):
                scored.append((len(q & set(tokenize(sentence))), doc_id, sentence))
        scored.sort(key=lambda x: -x[0])
        # Keep the best sentence plus a runner-up that scores almost as well (at most two).
        best = [s for s in scored[:2] if s[0] > 0 and s[0] >= scored[0][0] - 1] or scored[:1]
        return json.dumps({
            "answer": " ".join(s[2] for s in best),
            "sources": sorted({s[1] for s in best}),
            "confidence": round(min(0.95, 0.5 + 0.1 * best[0][0]), 2),
            "status": "answered",
        })


class ScriptedLLM:
    name = "scripted"

    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.calls = 0

    def generate(self, system: str, question: str, references: dict[str, str], strict: bool = False) -> str:
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return out


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, model: str | None = None):
        import anthropic  # optional dependency

        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("GUARDRAILS_MODEL", "claude-sonnet-5-5")

    def generate(self, system: str, question: str, references: dict[str, str], strict: bool = False) -> str:
        context = "\n".join(f"[{k}] {v}" for k, v in references.items()) or "(no documents found)"
        prompt = f"Reference documents:\n{context}\n\nStudent question: {question}"
        if strict:
            from guardrails.config import STRICT_REMINDER

            prompt += "\n\n" + STRICT_REMINDER
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")


def default_llm():
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicLLM()
        except ImportError:
            pass
    return MockLLM()
