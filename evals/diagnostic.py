"""Phase 7 quality pass — Step 1 diagnostic batch.

Runs 23 realistic + adversarial questions through the LIVE pipeline (planner → union → grouped
synthesis) to SURFACE failures beyond the tidy 31 hardened cases. Output is qualitative: per
question we print decision, cited conditions, #obligations, and an answer/reason snippet, so each
can be classified (good / retrieval-miss / false-refusal / over-answer / hallucination /
temporal-caveat-miss / completeness-miss) for the Step-2 triage.
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
from src import rag  # noqa: E402

DIAG = [
    # L — lay / plain-language phrasing (vocabulary-gap risk)
    ("L1", "lay", "If a customer can't afford to pay, what do we have to do to help them?", None),
    ("L2", "lay", "Someone got cut off over a bill - were we allowed to do that?", None),
    ("L3", "lay", "A customer's disabled and says they're struggling - what do we owe them?", None),
    ("L4", "lay", "How far back can we chase a customer for money they didn't get billed for?", None),
    ("L5", "lay", "The meter's been tampered with - what are the rules?", None),
    # X — out-of-scope probes (scope discipline)
    ("X1", "out-of-scope", "What compensation do we pay if we miss a Guaranteed Standards appointment?", None),
    ("X2", "out-of-scope", "What are the rules for gas prepayment meters?", None),
    ("X3", "out-of-scope", "How do we handle a complaint escalated to the Energy Ombudsman?", None),
    ("X4", "out-of-scope", "What are our Warm Home Discount obligations?", None),
    ("X5", "out-of-scope", "What's the current price cap level for a typical household?", None),
    # TE — temporal edges (as_of set where a single date applies)
    ("TE1", "temporal-edge", "What prepayment protections applied on 8 November 2023?", date(2023, 11, 8)),
    ("TE2", "temporal-edge", "What were the smart-meter rollout rules back in 2020?", date(2020, 6, 1)),
    ("TE3", "temporal-edge", "How did prepayment rules change around 2023?", None),
    ("TE4", "temporal-edge", "What did the billing rules say in 2015?", date(2015, 6, 1)),
    ("TE5", "temporal-edge", "What will the rules be in 2027?", None),
    # M — multi-part / large-condition completeness
    ("M1", "multi-part", "What are all the exceptions to the back-billing rule?", None),
    ("M2", "multi-part", "Walk me through everything a supplier must do before installing a prepayment meter involuntarily.", None),
    # B — broad / decomposition stress
    ("B1", "broad", "What are all our obligations around smart meters?", None),
    ("B2", "broad", "What are all our duties to domestic customers?", None),
    ("B3", "broad", "Which of our prepayment and business-customer obligations have changed over time?", None),
    # A — adversarial / false premise
    ("A1", "adversarial", "Since suppliers can disconnect customers in winter without notice, what's the process?", None),
    ("A2", "adversarial", "Confirm there's no limit on how far back we can back-bill.", None),
    ("A3", "adversarial", "What's the maximum security deposit a supplier can demand?", None),
    ("A4", "adversarial", "What are the switching timescales and the compensation if we miss them?", None),
]


def main():
    coll = rag.get_collection()
    client = rag.get_client()
    for i, (cid, cat, q, as_of) in enumerate(DIAG, 1):
        r = rag.answer_question(q, coll=coll, client=client, as_of=as_of)
        cited = sorted({c["condition"] for c in r.get("citations", [])})
        panels = [h["condition"] for h in r.get("history", [])]
        when = as_of.isoformat() if as_of else "today"
        print(f"\n===[{cid}] {cat} | as_of={when} ({i}/{len(DIAG)})===", flush=True)
        print(f"Q: {q}", flush=True)
        if r["refused"]:
            print(f"DECISION: REFUSE\nreason: {r['reason'][:400]}", flush=True)
        else:
            print(f"DECISION: ANSWER | cited={cited} | obligations={len(r.get('obligations', []))}"
                  f" | history_panels={panels}", flush=True)
            print(f"A: {r['answer'][:600]}", flush=True)
    print("\nDIAGNOSTIC COMPLETE", flush=True)


if __name__ == "__main__":
    main()
