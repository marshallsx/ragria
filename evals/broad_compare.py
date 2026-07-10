"""Phase 7 — Step 2 comparison: planner union vs the Step-0 baseline.

For each verified anchor query, compare the CONDITIONS surfaced by:
  * baseline : current single-query retrieval, served k=6 (what the app feeds today).
  * planned  : corpus-aware planner → per-sub-query hybrid retrieve → round-robin union (budget 40).
Metrics: Core recall (Core surfaced / Core), and precision noise (conditions outside Core∪Borderline).
Uses the planner (a few cheap Opus calls) + local retrieval; no re-embed.
"""
import sys
from pathlib import Path

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from src import rag, planner            # noqa: E402
from broad_baseline import ANCHORS, served_conditions, _ordered_conditions  # noqa: E402


def planned_conditions(q, coll):
    p, union = planner.plan_and_retrieve(q, coll=coll)
    return _ordered_conditions(c["meta"]["condition"] for c in union), union, p


def main():
    coll = rag.get_collection()
    print("Phase 7 Step-2 — planner union vs baseline (Core recall + precision noise).\n")
    print(f"{'ID':<5}{'baseline':<11}{'planned':<10}{'#subq':<7}{'planned noise (outside Core∪Borderline)'}")
    b_srv = p_srv = tot_core = 0
    for a in ANCHORS:
        core, bl = a["core"], a["borderline"]
        base = set(served_conditions(a["q"], coll))
        plist, union, p = planned_conditions(a["q"], coll)
        pset = set(plist)
        rb, rp = len(core & base), len(core & pset)
        noise = sorted(pset - core - bl)
        b_srv += rb; p_srv += rp; tot_core += len(core)
        nsub = len(p["subqueries"])
        print(f"{a['id']:<5}{f'{rb}/{len(core)}':<11}{f'{rp}/{len(core)}':<10}{nsub:<7}"
              f"{('clean' if not noise else '+'+str(noise))} "
              f"[union {len(union)} chunks]")
    print(f"\nAGGREGATE Core recall — baseline {b_srv}/{tot_core} ({b_srv/tot_core:.0%})  "
          f"→  planned {p_srv}/{tot_core} ({p_srv/tot_core:.0%})")
    print("Target: broad recall UP, narrow control (BQ5) unchanged, precision noise not materially worse.")


if __name__ == "__main__":
    main()
