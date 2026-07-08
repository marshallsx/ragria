"""
Phase 5 — Lightweight eval runner.

Runs the cases in evals/cases.yaml through answer_question() and grades
deterministically:
  - decision correctness: answered-vs-refused matches `expected`
  - retrieval hit: an expected condition appears in the top-k retrieved set
  - citation hit:  an expected condition appears in the model's citations

Prints a per-case table + summary, and writes evals/results_<label>.json.

Usage:
    venv/bin/python evals/run_evals.py --label baseline
    venv/bin/python evals/run_evals.py --label haiku --model claude-haiku-4-5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rag import MODEL, answer_question, get_client, get_collection  # noqa: E402

CASES = ROOT / "evals" / "cases.yaml"


def run(label: str, model: str) -> dict:
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    coll, client = get_collection(), get_client()

    rows = []
    for c in cases:
        as_of = c.get("as_of")  # YAML parses YYYY-MM-DD to a date; strings also allowed
        if isinstance(as_of, str):
            as_of = date.fromisoformat(as_of)
        r = answer_question(c["question"], coll=coll, client=client, model=model, as_of=as_of)
        retrieved = {m["condition"] for m in r["retrieved"]}
        cited = {ci["condition"] for ci in r["citations"]}
        expect = set(c["expect_conditions"])

        decision_ok = (c["expected"] == "refuse") == r["refused"]
        ret_hit = bool(expect & retrieved) if c["expected"] == "answer" else None
        cite_hit = bool(expect & cited) if c["expected"] == "answer" else None
        want = c.get("expect_contains")
        contains_ok = (want.lower() in (r.get("answer") or "").lower()) if want else None

        rows.append({
            "id": c["id"], "category": c["category"], "expected": c["expected"],
            "as_of": as_of.isoformat() if as_of else None,
            "refused": r["refused"], "decision_ok": decision_ok,
            "ret_hit": ret_hit, "cite_hit": cite_hit, "contains_ok": contains_ok,
            "expect_conditions": c["expect_conditions"],
            "retrieved": sorted(retrieved), "cited": sorted(cited),
        })

    # --- aggregate ---
    n = len(rows)
    decision_acc = sum(r["decision_ok"] for r in rows)
    answer_rows = [r for r in rows if r["expected"] == "answer"]
    ret_hits = sum(bool(r["ret_hit"]) for r in answer_rows)
    cite_hits = sum(bool(r["cite_hit"]) for r in answer_rows)
    false_refusals = [r["id"] for r in rows if r["expected"] == "answer" and r["refused"]]
    correct_refusals = [r["id"] for r in rows if r["expected"] == "refuse" and r["refused"]]
    false_answers = [r["id"] for r in rows if r["expected"] == "refuse" and not r["refused"]]
    content_rows = [r for r in rows if r["contains_ok"] is not None]
    content_ok = sum(bool(r["contains_ok"]) for r in content_rows)

    summary = {
        "label": label, "model": model, "n": n,
        "decision_accuracy": f"{decision_acc}/{n}",
        "retrieval_hit_rate": f"{ret_hits}/{len(answer_rows)}",
        "citation_hit_rate": f"{cite_hits}/{len(answer_rows)}",
        "content_checks": f"{content_ok}/{len(content_rows)}",
        "false_refusals": false_refusals,
        "correct_refusals": correct_refusals,
        "false_answers": false_answers,
    }

    # --- print ---
    print(f"\n=== {label}  (model {model}) ===")
    print(f"{'id':<4} {'cat':<11} {'exp':<7} {'decision':<9} {'ret':<4} {'cite':<5} {'cont':<5} retrieved -> cited")
    for r in rows:
        dec = "OK" if r["decision_ok"] else "WRONG"
        ret = "-" if r["ret_hit"] is None else ("hit" if r["ret_hit"] else "MISS")
        cite = "-" if r["cite_hit"] is None else ("hit" if r["cite_hit"] else "miss")
        con = "-" if r["contains_ok"] is None else ("ok" if r["contains_ok"] else "MISS")
        aso = f" @{r['as_of']}" if r.get("as_of") else ""
        print(f"{r['id']:<4} {r['category']:<11} {r['expected']:<7} {dec:<9} {ret:<4} {cite:<5} {con:<5} "
              f"{r['retrieved']} -> {r['cited']}{aso}")
    print("-" * 70)
    for k, v in summary.items():
        print(f"  {k}: {v}")

    out = ROOT / "evals" / f"results_{label}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(f"  written: {out.relative_to(ROOT)}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    run(args.label, args.model)
