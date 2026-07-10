"""Phase 7 cost A/B — does a HAIKU planner decompose as well as OPUS?

The planner is one LLM call per query; on the live paid demo it adds cost on top of synthesis.
Broad-query recall is determined by planner + retrieval (NOT synthesis), so we can measure the
planner's quality directly: run each anchor's plan_and_retrieve under Opus vs Haiku planning and
compare Core-condition recall of the union. If Haiku holds recall, switch the planner to Haiku and
keep Opus for synthesis — a free cost cut. (Planner calls only; no synthesis.)
"""
import sys
from pathlib import Path

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from src import rag, planner              # noqa: E402
from broad_baseline import ANCHORS, _ordered_conditions  # noqa: E402

OPUS = rag.MODEL
HAIKU = "claude-haiku-4-5-20251001"


def measure(model):
    coll = rag.get_collection()
    tot_hit = tot_core = 0
    rows = []
    for a in ANCHORS:
        core = a["core"]
        p, union = planner.plan_and_retrieve(a["q"], coll=coll, model=model)
        conds = set(_ordered_conditions(c["meta"]["condition"] for c in union))
        hit = len(core & conds)
        tot_hit += hit
        tot_core += len(core)
        rows.append((a["id"], f"{hit}/{len(core)}", f"{len(p['subqueries'])}sq", p.get("is_broad")))
    return tot_hit, tot_core, rows


def main():
    for label, model in (("OPUS  planner", OPUS), ("HAIKU planner", HAIKU)):
        h, c, rows = measure(model)
        print(f"\n{label}: Core recall {h}/{c} ({h/c:.0%})")
        for rid, rec, sq, broad in rows:
            print(f"    {rid}: {rec:<6} {sq:<5} is_broad={broad}")
    print("\nPLANNER AB DONE — if HAIKU recall matches OPUS, switch the planner to Haiku "
          "(keep Opus synthesis) for a per-query cost cut.")


if __name__ == "__main__":
    main()
