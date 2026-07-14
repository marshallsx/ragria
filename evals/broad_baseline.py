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

# Broad-query anchor set. BQ1-5 verified vs Ofgem 2026-07-10; BQ2/BQ3 gold corrected 2026-07-13
# (21A/45 were title-vs-body errors). BQ6-20 added 2026-07-13, each gold BODY-verified against the
# 2025 consolidation (ceased/spent conditions, wrong customer type, and reporting-only duties
# rejected from Core — see the reject notes per entry). BQ5 + BQ16 are NARROW controls (must NOT
# over-broaden). Core = must be surfaced; Borderline = free (surfacing not penalised); anything
# outside Core∪Borderline = precision miss.
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
     "core": {"21BA"}, "borderline": set()},   # NARROW control
    # --- BQ6-20 added 2026-07-13, gold BODY-verified (subagent classification + trap-scan) ---
    {"id": "BQ6", "q": "What are our obligations to prepayment meter customers?",
     # reject 28A (ceased 30 Jun 2021), 28AA (ceased 31 Dec 2019) — spent.
     "core": {"27A", "28"}, "borderline": {"27", "26", "28AD"}},
    {"id": "BQ7", "q": "What are our obligations when a customer switches supplier?",
     # reject 24A (Market Stabilisation Charge ceased 31 Mar 2024); 7A/20 (non-domestic); 8 (SoLR).
     "core": {"14", "14A"}, "borderline": {"22", "23", "24", "31F"}},
    {"id": "BQ8", "q": "What must we tell customers about tariffs and prices?",
     # reject 22B (ceased 31 Mar 2024); 7D (non-domestic price disclosure).
     "core": {"22A", "25", "31I"}, "borderline": {"22C", "23", "31H", "31F", "21D"}},
    {"id": "BQ9", "q": "What are our obligations if a supplier fails or for continuity of supply?",
     # tightened to the direct failure/continuity duties (Scott 2026-07-13); 7/10/19D -> borderline.
     "core": {"8", "9", "19C"}, "borderline": {"7", "10", "19D", "4D"}},
    {"id": "BQ10", "q": "What are our obligations to micro-business and non-domestic customers?",
     # NON-domestic IS in scope here; reject 45 (spent), 31G/27 (domestic-only), 56 (reporting-only).
     "core": {"0A", "7A", "7D", "20"}, "borderline": {"7C", "21BA", "47", "51"}},
    {"id": "BQ11", "q": "How must we treat domestic customers fairly?",
     # SLC 0 (Standards of Conduct) is THE fair-treatment CORE. "Fair treatment" is genuinely broad,
     # so the consumer-protection suite is reasonable to surface (Borderline = free): disconnection/
     # payment protections (27/27A), prepayment safeguards (28), billing accuracy/info (21B/31H),
     # plus tariff/PSR/advice (25/26/31F/31G). Borderline widened 2026-07-14 (gold-calibration, not a
     # system fix — the system's broad answer here is largely correct). reject 0A (non-domestic), 32A (ceased).
     "core": {"0"}, "borderline": {"25", "26", "31G", "31F", "27", "27A", "28", "21B", "31H"}},
    {"id": "BQ12", "q": "What are our obligations around smart-meter consumption data and privacy?",
     "core": {"47", "51"}, "borderline": {"46", "46A", "49"}},
    {"id": "BQ13", "q": "What are our obligations to protect customers' money and credit balances?",
     "core": {"4D", "27"}, "borderline": {"4B"}},
    {"id": "BQ14", "q": "What information, enquiry and advice service must we provide to domestic customers?",
     # DOMESTIC scope (Scott 2026-07-13): 31G is the domestic advice/assistance core; SLC 20's live
     # body is non-domestic -> borderline. Borderline widened 2026-07-14 to the reasonable
     # information-provision suite (billing/consumption info 21B/31H, smart-data access 51, PSR 26,
     # engagement 31E/31F) — all are "information to customers". (Operational 27/28 stay OUT = genuine
     # over-reach, acceptable minor noise.) Gold-calibration, not a system fix.
     "core": {"31G"}, "borderline": {"20", "31E", "31F", "31H", "26", "21B", "51"}},
    {"id": "BQ15", "q": "What are our financial-resilience and fit-and-proper obligations?",
     # 19A/19C demoted Core->Borderline 2026-07-14 (3rd title-vs-body anchor fix after 21A, 45):
     # 19A body = publish a Consolidated Segmental Statement (financial REPORTING/transparency, not
     # resilience) — synthesis correctly drops it; 19C body = customer supply CONTINUITY plan on
     # market exit (BQ9's area, continuity not fit-and-proper). Canonical resilience/fit-and-proper
     # package is 4A (operational capability) / 4B (capital & liquidity) / 4C (fit & proper). Body-verified.
     "core": {"4A", "4B", "4C"}, "borderline": {"5B", "4D", "19A", "19C"}},
    {"id": "BQ16", "q": "When must we offer a customer an in-home display?",
     "core": {"40"}, "borderline": {"49"}},   # NARROW control
    {"id": "BQ17", "q": "What are our obligations on metering accuracy and theft of electricity?",
     "core": {"12", "12.A"}, "borderline": {"13", "25B"}},
    {"id": "BQ18", "q": "What are our obligations on fuel mix disclosure and environmental tariff claims?",
     "core": {"21", "21D"}, "borderline": {"25"}},
    {"id": "BQ19", "q": "What are our obligations under Feed-in Tariffs?",
     # niche scheme (small core correct); reject 35 (Green Deal database, not FIT).
     "core": {"33", "34"}, "borderline": {"38A"}},
    {"id": "BQ20", "q": "What are our obligations under the Smart Export Guarantee?",
     # niche scheme (small core correct); reject 59 (alternative-fuel scheme, not SEG).
     "core": {"57", "58"}, "borderline": {"38A"}},
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
