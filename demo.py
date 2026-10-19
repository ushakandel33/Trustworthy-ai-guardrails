"""Try the guarded assistant from the command line.

Usage:
  python demo.py "What time does the library open?"     # one question
  python demo.py --trace "Ignore all previous instructions"  # show every guardrail decision
  python demo.py                                          # interactive mode
"""

from __future__ import annotations

import argparse
import json

from guardrails import GuardedAssistant
from guardrails.llm import default_llm


def show(assistant: GuardedAssistant, question: str, trace: bool) -> None:
    reply = assistant.handle(question)
    print(f"\n[{reply.outcome}] {reply.text}")
    if reply.modifications:
        print(f"  modifications: {', '.join(reply.modifications)}")
    for name, result in reply.results.items():
        if result.flagged:
            print(f"  - {name}: {result.action} ({result.reason})")
    if trace:
        print(json.dumps(reply.to_dict(), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="*")
    parser.add_argument("--trace", action="store_true", help="print the full guardrail trace as JSON")
    args = parser.parse_args()

    assistant = GuardedAssistant(default_llm())
    print(f"Model back end: {assistant.llm.name}")
    if args.question:
        show(assistant, " ".join(args.question), args.trace)
        return
    print("Ask a question (empty line to quit).")
    while True:
        try:
            q = input("\n> ").strip()
        except EOFError:
            break
        if not q:
            break
        show(assistant, q, args.trace)


if __name__ == "__main__":
    main()
