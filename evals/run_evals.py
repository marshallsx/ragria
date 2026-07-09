"""
Phase 5 + eval-hardening — eval runner.

Runs the cases in evals/cases.yaml through answer_question() and grades:

Deterministic:
  - decision correctness   : answered-vs-refused matches `expected`
  - retrieval hit + RANK    : is an expected condition in the top-k, and at what rank
                              (→ recall@1/@3/@6, mean rank)
  - citation hit            : an expected condition appears in the model's citations
  - content check           : `expect_contains` substring present in the answer
  - version check           : `expect_version` = the held version actually served (temporal swap)
  - history check           : `expect_history` = a "what changed" view of that kind is produced

LLM-judged:
  - faithfulness/groundedness: an independent Claude call judges whether EVERY claim in the
    answer is supported by the retrieved extracts (direct hallucination measure). --no-judge skips.

Prints a per-case table + summary, and writes evals/results_<label>.json.

Usage:
    venv/bin/python evals/run_evals.py --label hardened
    venv/bin/python evals/run_evals.py --label lean --no-judge
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

# --- Faithfulness / groundedness judge (independent LLM check for hallucination) ---
FAITH_SYSTEM = """You are a strict grounding checker for a retrieval-augmented answer about energy \
regulation. You are given the SOURCE MATERIAL that was provided to a model — this includes the current \
licence version and the as-of date, verified temporal facts (dated from Ofgem modification notices), \
and the retrieved licence extracts — plus the ANSWER the model produced. Decide whether EVERY factual \
claim in the ANSWER is supported by the SOURCE MATERIAL.

- Claims about dates, numbers, obligations, and condition references must be traceable to the source material.
- Statements of the current version or the as-of date (e.g. "as of 1 August 2025") are supported when
  the source material states them.
- Pure framing/transition sentences that assert no fact are fine.
- If the answer says it cannot confirm something, or declines/refuses, that is faithful (not a claim).
- Set faithful=false ONLY if the answer asserts a fact the source material does not support (a
  hallucination), and list the unsupported claim(s). Be strict but fair."""

FAITH_SCHEMA = {
    "type": "object",
    "properties": {
        "faithful": {"type": "boolean"},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["faithful", "unsupported_claims", "reason"],
    "additionalProperties": False,
}


def judge_faithfulness(answer: str, source: str, client, model: str) -> dict:
    user = (f"SOURCE MATERIAL (everything the model was given, including the question):\n\n{source}"
            f"\n\n---\n\nANSWER TO CHECK:\n\n{answer}")
    fmt = {"type": "json_schema", "schema": FAITH_SCHEMA}
    kwargs = dict(model=model, max_tokens=1024, system=FAITH_SYSTEM,
                  messages=[{"role": "user", "content": user}])
    if "haiku" in model:
        kwargs["output_config"] = {"format": fmt}
    else:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": "low", "format": fmt}
    resp = client.messages.create(**kwargs)
    txt = next(b.text for b in resp.content if b.type == "text")
    return json.loads(txt)


def run(label: str, model: str, judge: bool = True) -> dict:
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    coll, client = get_collection(), get_client()

    rows = []
    for c in cases:
        as_of = c.get("as_of")  # YAML parses YYYY-MM-DD to a date; strings also allowed
        if isinstance(as_of, str):
            as_of = date.fromisoformat(as_of)
        r = answer_question(c["question"], coll=coll, client=client, model=model, as_of=as_of)
        ordered = [m["condition"] for m in r["retrieved"]]          # fused-rank order
        retrieved = set(ordered)
        cited = {ci["condition"] for ci in r["citations"]}
        expect = set(c["expect_conditions"])
        is_answer = c["expected"] == "answer"

        decision_ok = (c["expected"] == "refuse") == r["refused"]
        ret_hit = bool(expect & retrieved) if is_answer else None
        # rank of the first expected condition in the retrieved list (1-based), else None
        rank = next((i + 1 for i, cnd in enumerate(ordered) if cnd in expect), None) if is_answer else None
        cite_hit = bool(expect & cited) if is_answer else None
        want = c.get("expect_contains")
        contains_ok = (want.lower() in (r.get("answer") or "").lower()) if want else None
        want_ver = c.get("expect_version")
        served = {m["condition"]: m.get("version") for m in r["retrieved"]}
        version_ok = any(served.get(cond) == want_ver for cond in expect) if want_ver else None
        want_hist = c.get("expect_history")
        hist_kind = {h["condition"]: h["kind"] for h in r.get("history", [])}
        history_ok = any(hist_kind.get(cond) == want_hist for cond in expect) if want_hist else None

        # Faithfulness judge (answered cases only).
        faithful, faith_reason = None, None
        if judge and is_answer and not r["refused"] and r.get("answer"):
            v = judge_faithfulness(r["answer"], r.get("prompt", ""), client, model)
            faithful, faith_reason = v["faithful"], (v.get("unsupported_claims") or v.get("reason"))

        rows.append({
            "id": c["id"], "category": c["category"], "expected": c["expected"],
            "as_of": as_of.isoformat() if as_of else None,
            "refused": r["refused"], "decision_ok": decision_ok,
            "ret_hit": ret_hit, "rank": rank, "cite_hit": cite_hit,
            "contains_ok": contains_ok, "version_ok": version_ok, "history_ok": history_ok,
            "faithful": faithful, "faith_note": faith_reason,
            "expect_conditions": c["expect_conditions"],
            "retrieved": ordered, "cited": sorted(cited),
        })

    # --- aggregate ---
    n = len(rows)
    decision_acc = sum(r["decision_ok"] for r in rows)
    answer_rows = [r for r in rows if r["expected"] == "answer"]
    n_ans = len(answer_rows)
    ret_hits = sum(bool(r["ret_hit"]) for r in answer_rows)
    cite_hits = sum(bool(r["cite_hit"]) for r in answer_rows)
    ranks = [r["rank"] for r in answer_rows if r["rank"]]
    recall_at = {k: sum(1 for r in answer_rows if r["rank"] and r["rank"] <= k) for k in (1, 3, 6)}
    mean_rank = round(sum(ranks) / len(ranks), 2) if ranks else None
    false_refusals = [r["id"] for r in rows if r["expected"] == "answer" and r["refused"]]
    correct_refusals = [r["id"] for r in rows if r["expected"] == "refuse" and r["refused"]]
    false_answers = [r["id"] for r in rows if r["expected"] == "refuse" and not r["refused"]]

    def frac(pred, rows_):
        sub = [r for r in rows_ if pred(r) is not None]
        return sub, sum(bool(pred(r)) for r in sub)

    content_rows, content_ok = frac(lambda r: r["contains_ok"], rows)
    version_rows, version_ok_n = frac(lambda r: r["version_ok"], rows)
    history_rows, history_ok_n = frac(lambda r: r["history_ok"], rows)
    faith_rows, faith_ok_n = frac(lambda r: r["faithful"], rows)
    unfaithful = [r["id"] for r in rows if r["faithful"] is False]

    summary = {
        "label": label, "model": model, "n": n, "judge": judge,
        "decision_accuracy": f"{decision_acc}/{n}",
        "retrieval_hit_rate": f"{ret_hits}/{n_ans}",
        "recall@1": f"{recall_at[1]}/{n_ans}", "recall@3": f"{recall_at[3]}/{n_ans}",
        "recall@6": f"{recall_at[6]}/{n_ans}", "mean_rank": mean_rank,
        "citation_hit_rate": f"{cite_hits}/{n_ans}",
        "content_checks": f"{content_ok}/{len(content_rows)}",
        "version_checks": f"{version_ok_n}/{len(version_rows)}",
        "history_checks": f"{history_ok_n}/{len(history_rows)}",
        "faithfulness": (f"{faith_ok_n}/{len(faith_rows)}" if faith_rows else "n/a (skipped)"),
        "unfaithful": unfaithful,
        "false_refusals": false_refusals,
        "correct_refusals": correct_refusals,
        "false_answers": false_answers,
    }

    # --- print ---
    print(f"\n=== {label}  (model {model}{', judge on' if judge else ', no judge'}) ===")
    hdr = f"{'id':<4} {'cat':<10} {'dec':<6} {'ret':<6} {'cite':<5} {'cont':<5} {'ver':<4} {'hist':<5} {'faith':<6}"
    print(hdr)
    for r in rows:
        dec = "OK" if r["decision_ok"] else "WRONG"
        ret = "-" if r["ret_hit"] is None else (f"@{r['rank']}" if r["ret_hit"] else "MISS")
        cite = "-" if r["cite_hit"] is None else ("hit" if r["cite_hit"] else "miss")
        con = "-" if r["contains_ok"] is None else ("ok" if r["contains_ok"] else "MISS")
        ver = "-" if r["version_ok"] is None else ("ok" if r["version_ok"] else "MISS")
        his = "-" if r["history_ok"] is None else ("ok" if r["history_ok"] else "MISS")
        fai = "-" if r["faithful"] is None else ("ok" if r["faithful"] else "BAD")
        print(f"{r['id']:<4} {r['category']:<10} {dec:<6} {ret:<6} {cite:<5} {con:<5} {ver:<4} {his:<5} {fai:<6}")
    print("-" * 60)
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
    ap.add_argument("--no-judge", action="store_true", help="skip the faithfulness LLM judge")
    args = ap.parse_args()
    run(args.label, args.model, judge=not args.no_judge)
