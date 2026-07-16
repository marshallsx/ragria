"""Synthesis-model cost A/B — is a cheaper model as good as Opus for grouped synthesis?

The planner is already Haiku; the expensive call in every broad answer is the Opus SYNTHESIS.
This screens cheaper synthesis models against Opus on the 20 body-verified broad anchors.

Design (cost-conscious):
- Compute plan+union ONCE per anchor (Haiku plan, model-independent), then run synthesis over the
  SAME union on each candidate model. One planner call per anchor; true apples-to-apples (identical
  context, only the synth model varies).
- Score answer-level Core recall + precision noise (cited outside Core u Borderline) + refused.
- Faithfulness (the safety gate) is deferred to the ship-gate; this is the cheap recall screen.

Run:  venv/bin/python evals/synth_model_ab.py
"""
import sys
from pathlib import Path

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))
from src import rag, planner            # noqa: E402
from broad_baseline import ANCHORS      # noqa: E402

OPUS = rag.MODEL                         # claude-opus-4-8 (current default)
SONNET = "claude-sonnet-5"
HAIKU = planner.HAIKU                    # claude-haiku-4-5-20251001

MODELS = [("opus", OPUS), ("sonnet", SONNET), ("haiku", HAIKU)]


def main():
    coll = rag.get_collection()
    client = rag.get_client()
    print("Synthesis-model A/B — answer-level Core recall + precision over 20 anchors.")
    print("Same union per anchor (Haiku plan); only the synthesis model varies.\n")

    # tot[name] = [hit, core]
    tot = {name: [0, 0] for name, _ in MODELS}
    noise_tot = {name: 0 for name, _ in MODELS}
    refused_tot = {name: 0 for name, _ in MODELS}

    header = f"{'ID':<5}" + "".join(f"{name:<24}" for name, _ in MODELS)
    print(header)
    print(f"{'':5}" + "".join(f"{'recall  noise  refused':<24}" for _ in MODELS))
    for a in ANCHORS:
        core, bl = a["core"], a["borderline"]
        # Plan + union ONCE (model-independent Haiku plan), reused across synthesis models.
        _p, union = planner.plan_and_retrieve(a["q"], coll=coll, client=client)
        row = f"{a['id']:<5}"
        for name, model in MODELS:
            res = planner.synthesize(a["q"], union, coll=coll, client=client, model=model)
            cited = {ci["condition"] for ci in res.get("citations", [])}
            hit = len(core & cited)
            noise = sorted(cited - core - bl)
            refused = bool(res.get("refused"))
            tot[name][0] += hit; tot[name][1] += len(core)
            noise_tot[name] += len(noise)
            refused_tot[name] += int(refused)
            cell = f"{hit}/{len(core)}  {'+'+str(len(noise)) if noise else 'clean':<6} {'REFUSED' if refused else ''}"
            row += f"{cell:<24}"
        print(row)

    print("\n" + "=" * 72)
    for name, _ in MODELS:
        h, c = tot[name]
        print(f"{name:<8} Core recall {h}/{c} ({h/c:.0%})   precision-noise conds={noise_tot[name]}   "
              f"refused={refused_tot[name]}")
    print("\n(Opus is the reference. A candidate is viable only if recall ~matches Opus AND refused=0.")
    print(" Faithfulness is checked at the ship-gate, not here.)")


if __name__ == "__main__":
    main()
