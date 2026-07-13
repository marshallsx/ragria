"""Phase 7 — Step 0 baseline (LOCAL, no API, no re-embed).

Measures the CURRENT retrieval pipeline's completeness on the verified anchor broad-query set,
BEFORE building the corpus-aware planner — so the planner's gain is measured, not assumed.

For each anchor query we report, on the set of CONDITIONS surfaced:
  * served  (k=TOP_K=6)   — what the live app actually feeds the model today.
  * ceiling (deep, k=40)  — everything the current retrievers can reach at depth. If a Core
                            condition isn't even here, deeper retrieval won't fix it → the case
                            for targeted sub-queries (planning) rather than just a bigger k.
Metrics: recall = Core surfaced / Core.  precision = did we surface anything OUTSIDE Core∪Borderline?
(expand_hits only expands conditions already in the hits, so the condition SET == retrieval's set.)
"""
import sys
from pathlib import Path

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
from src import rag  # noqa: E402  (loads Chroma collection + BM25 lazily; no API)

DEEP = 40  # ceiling depth

# Verified vs Ofgem 2026-07-10 (tasks/todo.md Phase 7).
ANCHORS = [
    {"id": "BQ1", "q": "What obligations do we have to vulnerable customers?",
     "core": {"0", "26", "27", "27A", "28"}, "borderline": {"31G", "0A"}},
    {"id": "BQ2", "q": "What are our billing obligations to domestic customers?",
     # 21A removed: its full text is the CRC (Carbon Reduction Commitment) Energy Efficiency Scheme
     # annual statement to non-domestic Participants — NOT a domestic billing obligation. The
     # domestic billing-information / statements duty is 31H (already Core). Corrected 2026-07-13.
     "core": {"21B", "21BA", "31H"}, "borderline": {"22A", "31I", "27"}},
    {"id": "BQ3", "q": "What must we do when installing a smart meter?",
     # 45 demoted Core -> Borderline: its body is "Smart Metering Consumer Engagement" — establishing
     # /funding a CENTRAL consumer-engagement body (Smart Energy GB), not an operational install duty,
     # AND it CEASED to apply on 30 Jun 2021 (spent in the 2025 consolidation). Synthesis correctly
     # excludes it for this operational install question; 39/40/41 are the real install duties.
     # Kept Borderline (not dropped) since it is smart-metering-related. Corrected 2026-07-13.
     "core": {"39", "40", "41"}, "borderline": {"42", "45", "46", "47", "51"}},
    {"id": "BQ4", "q": "What are our obligations before disconnecting a customer for debt?",
     "core": {"27", "27A", "28"}, "borderline": {"26", "0"}},
    {"id": "BQ5", "q": "What is the maximum back-billing period for domestic customers?",
     "core": {"21BA"}, "borderline": set()},
]


def served_conditions(q, coll):
    """Conditions in the fused top-TOP_K chunks — what the app serves today."""
    fused, _ = rag.hybrid_retrieve(q, rag.TOP_K, coll)
    return _ordered_conditions(h["meta"]["condition"] for h in fused)


def ceiling_conditions(q, coll):
    """Conditions reachable by deep retrieval: vector@DEEP ∪ BM25@DEEP."""
    vconds = [h["meta"]["condition"] for h in rag.vector_retrieve(q, DEEP, coll)]
    bm25, ids, cbi = rag.get_bm25()
    scores = bm25.get_scores(rag.expand_query(q))
    top = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)[:DEEP]
    bconds = [cbi[ids[i]]["metadata"]["condition"] for i in top]
    return _ordered_conditions(vconds + bconds)


def _ordered_conditions(cond_iter):
    seen = []
    for c in cond_iter:
        if c not in seen:
            seen.append(c)
    return seen


def main():
    coll = rag.get_collection()
    print(f"Phase 7 Step-0 baseline — current retrieval, {len(ANCHORS)} anchor queries "
          f"(served k={rag.TOP_K}, ceiling k={DEEP}). LOCAL, no API.\n")
    print(f"{'ID':<5}{'recall_served':<15}{'recall_ceiling':<16}{'precision':<11}missing_core (served | unreachable)")
    agg_srv = agg_ceil = agg_core = 0
    noisy = 0
    for a in ANCHORS:
        core, bl = a["core"], a["borderline"]
        served = set(served_conditions(a["q"], coll))
        ceiling = set(ceiling_conditions(a["q"], coll))
        rs = len(core & served)
        rc = len(core & ceiling)
        outside = served - core - bl                     # precision: surfaced noise
        miss_served = core - served
        miss_unreach = core - ceiling                    # Core not even reachable at depth → needs planning
        agg_srv += rs; agg_ceil += rc; agg_core += len(core)
        if outside:
            noisy += 1
        prec = "clean" if not outside else f"+{sorted(outside)}"
        print(f"{a['id']:<5}{rs}/{len(core):<13}{rc}/{len(core):<14}{prec:<11}"
              f"{sorted(miss_served)} | {sorted(miss_unreach)}")
    print(f"\nAGGREGATE Core recall — served {agg_srv}/{agg_core} "
          f"({agg_srv/agg_core:.0%}) · ceiling {agg_ceil}/{agg_core} ({agg_ceil/agg_core:.0%})")
    print(f"Queries with precision noise (served a non-Core, non-Borderline condition): {noisy}/{len(ANCHORS)}")
    print("\nRead: low served + HIGH ceiling recall ⇒ planning/deeper retrieval will help. "
          "Low ceiling recall ⇒ Core is unreachable even at depth ⇒ targeted sub-queries needed.")


if __name__ == "__main__":
    main()
