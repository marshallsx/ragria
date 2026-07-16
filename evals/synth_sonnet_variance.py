"""Sonnet synthesis — broad-anchor variance passes (confirm the screen's 47/47 is stable).

The synth_model_ab screen gave ONE Sonnet pass = 47/47 (matched Opus). Answer-level is
non-deterministic, so this runs N more Sonnet passes over the 20 anchors to confirm stability.
Reuses one plan+union per anchor per pass (Haiku plan); only Sonnet synthesis runs.

Run:  venv/bin/python evals/synth_sonnet_variance.py [passes]
"""
import sys
from pathlib import Path

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from src import rag, planner            # noqa: E402
from broad_baseline import ANCHORS      # noqa: E402

SONNET = "claude-sonnet-5"


def main():
    passes = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    coll = rag.get_collection()
    client = rag.get_client()
    print(f"Sonnet synthesis — {passes} broad-anchor variance passes (Core recall + noise).\n")
    for p in range(1, passes + 1):
        tot_hit = tot_core = noise = refused = 0
        cells = []
        for a in ANCHORS:
            core, bl = a["core"], a["borderline"]
            _pl, union = planner.plan_and_retrieve(a["q"], coll=coll, client=client)
            res = planner.synthesize(a["q"], union, coll=coll, client=client, model=SONNET)
            cited = {ci["condition"] for ci in res.get("citations", [])}
            hit = len(core & cited)
            n = len(cited - core - bl)
            tot_hit += hit; tot_core += len(core); noise += n; refused += int(bool(res.get("refused")))
            cells.append(f"{a['id']}:{hit}/{len(core)}" + (f"+{n}" if n else "") + ("R" if res.get("refused") else ""))
        print(f"pass {p}: Core recall {tot_hit}/{tot_core} ({tot_hit/tot_core:.0%})  "
              f"noise={noise}  refused={refused}")
        print("   " + "  ".join(cells) + "\n")


if __name__ == "__main__":
    main()
