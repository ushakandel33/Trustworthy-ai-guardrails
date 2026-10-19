"""Run the labelled test suite and write results and metrics to results/.

Usage:  python evaluate.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from guardrails import GuardedAssistant
from guardrails.llm import MockLLM, ScriptedLLM

ROOT = Path(__file__).parent
GUARDRAILS = ["input_pii", "prompt_injection", "sensitive_topic", "schema", "groundedness", "output_sensitive"]


def run_case(case: dict) -> dict:
    llm = ScriptedLLM(case["llm_outputs"]) if case.get("llm_outputs") else MockLLM()
    reply = GuardedAssistant(llm).handle(case["input"])
    flags = reply.flags()
    expected = set(case["expected_flags"])

    problems = []
    if reply.outcome != case["expected_outcome"]:
        problems.append(f"outcome {reply.outcome} != {case['expected_outcome']}")
    for name in GUARDRAILS:
        if name not in flags:
            if name in expected:
                problems.append(f"{name} did not run")
            continue
        if flags[name] != (name in expected):
            problems.append(f"{name} {'fired' if flags[name] else 'missed'}")
    topic = reply.results["sensitive_topic"].details.get("category")
    if case.get("expected_topic") and topic != case["expected_topic"]:
        problems.append(f"topic {topic} != {case['expected_topic']}")

    return {
        "id": case["id"],
        "group": case["group"],
        "input": case["input"],
        "reference_docs": ", ".join(reply.references) or "-",
        "scripted_output": " || ".join(case.get("llm_outputs", [])) or "(mock model)",
        "expected": f"{case['expected_outcome']} ({', '.join(sorted(expected)) or 'no flags'})",
        "actual": f"{reply.outcome} ({', '.join(sorted(k for k, v in flags.items() if v)) or 'no flags'})",
        "modifications": ", ".join(reply.modifications) or "-",
        "response": reply.text,
        "status": "PASS" if not problems else "FAIL",
        "problems": "; ".join(problems),
        "note": case.get("note", ""),
        "_flags": flags,
        "_expected": sorted(expected),
        "_trace": reply.to_dict(),
    }


def confusion(rows: list[dict]) -> dict:
    metrics = {}
    for name in GUARDRAILS:
        tp = fp = fn = tn = 0
        fps, fns = [], []
        for r in rows:
            if name not in r["_flags"]:
                continue  # guardrail never ran for this case (request stopped earlier)
            pred, truth = r["_flags"][name], name in r["_expected"]
            if pred and truth:
                tp += 1
            elif pred:
                fp += 1
                fps.append(r["id"])
            elif truth:
                fn += 1
                fns.append(r["id"])
            else:
                tn += 1
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
        metrics[name] = {
            "evaluated": tp + fp + fn + tn, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": None if precision is None else round(precision, 2),
            "recall": None if recall is None else round(recall, 2),
            "f1": None if f1 is None else round(f1, 2),
            "false_positives": fps, "false_negatives": fns,
        }
    return metrics


def fmt(v):
    return "n/a" if v is None else f"{v:.2f}"


def main() -> None:
    cases = json.loads((ROOT / "tests" / "test_cases.json").read_text())
    rows = [run_case(c) for c in cases]
    metrics = confusion(rows)
    passed = sum(r["status"] == "PASS" for r in rows)
    by_group: dict[str, list[int]] = {}
    for r in rows:
        g = by_group.setdefault(r["group"], [0, 0])
        g[0] += r["status"] == "PASS"
        g[1] += 1

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    public = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    with open(out / "test_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(public[0]))
        w.writeheader()
        w.writerows(public)
    (out / "traces.json").write_text(json.dumps({r["id"]: r["_trace"] for r in rows}, indent=2))
    summary = {"total": len(rows), "passed": passed, "failed": len(rows) - passed,
               "pass_rate": round(passed / len(rows), 2), "by_group": by_group, "guardrails": metrics}
    (out / "metrics.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "# Evaluation results", "",
        f"**{passed} of {len(rows)} test cases passed ({passed / len(rows):.0%}).**", "",
        "## Pass rate by test group", "", "| Group | Passed | Total |", "|---|---|---|",
        *[f"| {g} | {p} | {t} |" for g, (p, t) in by_group.items()], "",
        "## Per-guardrail metrics", "",
        "A guardrail is scored only on cases where it actually ran (output guardrails do not run on blocked requests).", "",
        "| Guardrail | Cases | TP | FP | FN | TN | Precision | Recall | F1 | False positives | False negatives |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *[f"| {n} | {m['evaluated']} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | {fmt(m['precision'])} | "
          f"{fmt(m['recall'])} | {fmt(m['f1'])} | {', '.join(m['false_positives']) or '-'} | {', '.join(m['false_negatives']) or '-'} |"
          for n, m in metrics.items()], "",
        "## All test cases", "",
        "| ID | Group | Input | Expected | Actual | Status | Problem |", "|---|---|---|---|---|---|---|",
        *[f"| {r['id']} | {r['group']} | {r['input'].replace('|', '/')} | {r['expected']} | {r['actual']} | {r['status']} | {r['problems'] or '-'} |" for r in rows],
    ]
    (out / "evaluation_summary.md").write_text("\n".join(lines) + "\n")

    print(f"{passed}/{len(rows)} passed")
    for r in rows:
        if r["status"] == "FAIL":
            print(f"  FAIL {r['id']}: {r['problems']}")
    print()
    for n, m in metrics.items():
        print(f"  {n:17} P={fmt(m['precision'])} R={fmt(m['recall'])} FP={m['false_positives']} FN={m['false_negatives']}")


if __name__ == "__main__":
    main()
