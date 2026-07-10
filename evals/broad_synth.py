"""Phase 7 — Step 3: ANSWER-LEVEL recall + precision of the grouped synthesis.

Retrieval recall (Step 2) is a ceiling; what matters is whether the synthesized ANSWER actually
surfaces each obligation. For each anchor query we run the full pipeline (plan → union → grouped
synthesis) and score the CITED conditions:
  recall    = Core conditions cited / Core
  precision = did the answer cite a condition OUTSIDE Core ∪ Borderline? (answer-level noise)
Also sanity: BQ5 (narrow control) must stay a tight, correct single-obligation answer.
Uses ~2 Opus calls per anchor (plan + synth); no re-embed.
"""
import sys
from pathlib import Path

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from src import rag, planner            # noqa: E402
from broad_baseline import ANCHORS      # noqa: E402


def main():
    coll = rag.get_collection()
    print("Phase 7 Step-3 — answer-level recall + precision (grouped synthesis).\n")
    print(f"{'ID':<5}{'recall(cited)':<14}{'#oblig':<8}{'refused':<9}{'precision noise (cited outside Core∪Borderline)'}")
    tot_hit = tot_core = 0
    for a in ANCHORS:
        core, bl = a["core"], a["borderline"]
        res = planner.answer_broad(a["q"], coll=coll)
        cited = {ci["condition"] for ci in res.get("citations", [])}
        hit = len(core & cited)
        noise = sorted(cited - core - bl)
        tot_hit += hit; tot_core += len(core)
        n_ob = len(res.get("obligations", []))
        print(f"{a['id']:<5}{f'{hit}/{len(core)}':<14}{n_ob:<8}{str(res.get('refused')):<9}"
              f"{'clean' if not noise else '+'+str(noise)}")
    print(f"\nAGGREGATE answer-level Core recall (CITED): {tot_hit}/{tot_core} ({tot_hit/tot_core:.0%})")
    print("(Compare: retrieval union recall was 100%. Synthesis recall <= retrieval; precision is the trade to watch.)")

    print("\n--- BQ1 sample answer (grouped) ---")
    res = planner.answer_broad(ANCHORS[0]["q"], coll=coll)
    for ob in res.get("obligations", []):
        cs = ", ".join(f"C{ci['condition']}" for ci in ob.get("citations", []))
        print(f"  • {ob.get('obligation','')}  [{cs}]")
    print(f"  note: {res.get('exhaustiveness_note','')}")


if __name__ == "__main__":
    main()
