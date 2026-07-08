"""
Phase 6 — Change detector (curation aid, not part of the serving path).

Diffs every Condition across the held consolidations on disk and classifies how it
changed over time, so we choose which conditions to map from DATA, not memory.

Method
------
Auto-discovers `data/raw/electricity-supply-slc-consolidated-*.pdf`, sorts them by
date, parses each into Conditions, and compares consecutive snapshots. With N held
snapshots you get N-1 intervals; three snapshots (2019, 2022, 2025) give two:
    I1 = 2019-08-03 -> 2022-04-14      I2 = 2022-04-14 -> 2025-08-01

Per condition it reports one of:
  - STABLE          present throughout, text unchanged in every interval
  - INTRODUCED      absent then present (existence-boundary candidate, e.g. 25E/4D)
  - REMOVED         present then absent / "Not used"
  - SINGLE-CHANGE   text changed in exactly ONE interval  -> clean text-change CANDIDATE
  - MULTI-CHANGE    text changed in >= 2 intervals         -> volatile, avoid (e.g. SLC 47)
  - ANOMALY         non-monotonic presence (removed then re-added)

IMPORTANT caveat (honest): a snapshot diff only sees the ENDPOINTS of an interval.
"SINGLE-CHANGE" means "changed once BETWEEN snapshots" — Ofgem may have modified the
condition several times within that interval and we only see the net difference. So
SINGLE-CHANGE is a *candidate* to confirm against Ofgem's modification history (as we
did for Condition 28), while MULTI-CHANGE is *confirmed* volatile. Resolution is only
as fine as the snapshots held.

Usage:
    venv/bin/python src/detect_changes.py
"""
from __future__ import annotations

import difflib
import re
import sys
from datetime import date
from pathlib import Path

from pypdf import PdfReader

try:  # to annotate conditions we have already mapped
    from src import temporal
except ImportError:  # pragma: no cover
    import temporal

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
REPORT = ROOT / "docs" / "change-map.md"

BODY_START = 7                         # cover=1, ToC=2..6 (same for every held version)
CHANGE_THRESH = 0.97                   # normalized-text ratio below this = "changed"
MIN_SUBSTANTIVE = 30                   # normalized chars; below this = absent / "Not used"

COND = re.compile(r"^Condition\s+(\d+[A-Z]{0,3}(?:\.[A-Z])?)[.:]\s+(.+)")
SECTION = re.compile(r"^(SECTION\s+[A-Z][0-9]?):")
_DATE_IN_NAME = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")


def is_boiler(l: str) -> bool:
    l = l.strip()
    if not l:
        return True
    if l.startswith("Note: Consolidated conditions"):
        return True
    if "Licence: Standard Conditions - Consolidated" in l:
        return True
    if l in ("Electricity", "suppliers"):
        return True
    return bool(re.fullmatch(r"\d{1,3}", l))  # standalone page number


def norm(s: str) -> str:
    s = (s.lower().replace("’", "'").replace("‘", "'")
         .replace("–", "-").replace("—", "-"))
    return re.sub(r"[^a-z0-9]", "", s)


def version_date(pdf: Path) -> date:
    m = _DATE_IN_NAME.search(pdf.name)
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    return date(y, mo, d)


def parse(pdf: Path) -> dict[str, dict]:
    """Condition number -> {title, raw, norm}. Later duplicate lines append."""
    reader = PdfReader(str(pdf))
    conds: dict[str, dict] = {}
    cur = None
    for i in range(BODY_START - 1, len(reader.pages)):
        for raw_line in (reader.pages[i].extract_text() or "").split("\n"):
            line = raw_line.strip()
            if is_boiler(line) or SECTION.match(line):
                continue
            m = COND.match(line)
            if m:
                cur = m.group(1)
                conds.setdefault(cur, {"title": m.group(2).strip(), "lines": []})
            elif cur is not None:
                conds[cur]["lines"].append(line)
    out = {}
    for c, v in conds.items():
        raw = " ".join(v["lines"]).strip()
        out[c] = {"title": v["title"], "raw": raw, "norm": norm(raw)}
    return out


def present(rec: dict | None) -> bool:
    return rec is not None and len(rec["norm"]) >= MIN_SUBSTANTIVE


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def classify(cond: str, versions: list[tuple[date, dict]]):
    """Return (klass, detail dict) for one condition across the ordered versions."""
    recs = [v.get(cond) for _, v in versions]
    pres = [present(r) for r in recs]

    # Presence transitions (monotonic checks).
    if not any(pres):
        return "EMPTY", {}
    # Non-monotonic: True...False...True
    seen_true = False
    seen_gap_after_true = False
    for p in pres:
        if p:
            if seen_gap_after_true:
                return "ANOMALY", {"presence": pres}
            seen_true = True
        elif seen_true:
            seen_gap_after_true = True

    first, last = pres[0], pres[-1]
    if not first and last:
        # Introduced somewhere; find the interval where it appears.
        for i in range(1, len(pres)):
            if not pres[i - 1] and pres[i]:
                return "INTRODUCED", {"interval": i, "presence": pres}
    if first and not last:
        for i in range(1, len(pres)):
            if pres[i - 1] and not pres[i]:
                return "REMOVED", {"interval": i, "presence": pres}

    # Present throughout — compare text across intervals.
    sims = []
    changed = []
    for i in range(1, len(versions)):
        s = ratio(recs[i - 1]["norm"], recs[i]["norm"])
        sims.append(s)
        changed.append(s < CHANGE_THRESH)
    n_changes = sum(changed)
    detail = {
        "sims": [round(s, 3) for s in sims],
        "changed_intervals": [i + 1 for i, ch in enumerate(changed) if ch],
        "chars": [len(recs[i]["raw"]) for i in range(len(recs))],
    }
    if n_changes == 0:
        return "STABLE", detail
    if n_changes == 1:
        return "SINGLE-CHANGE", detail
    return "MULTI-CHANGE", detail


def already_mapped(cond: str) -> str:
    if cond in getattr(temporal, "TEXT_CHANGES", {}):
        return " (MAPPED: text-change)"
    if cond in getattr(temporal, "MAPPED", {}):
        return " (MAPPED: existence)"
    return ""


def main() -> int:
    pdfs = sorted(RAW.glob("electricity-supply-slc-consolidated-*.pdf"), key=version_date)
    if len(pdfs) < 2:
        print("Need >= 2 consolidations in data/raw/ to diff.", flush=True)
        return 1

    versions = []
    print("Parsing held consolidations:", flush=True)
    for p in pdfs:
        d = version_date(p)
        conds = parse(p)
        versions.append((d, conds))
        print(f"  {d.isoformat()}  {p.name}  ({len(conds)} conditions)", flush=True)

    labels = [d.isoformat() for d, _ in versions]
    intervals = [f"I{i} = {labels[i-1]} -> {labels[i]}" for i in range(1, len(labels))]

    all_conds = sorted(
        {c for _, v in versions for c in v},
        key=lambda c: (int(re.match(r"\d+", c).group()), c),
    )
    buckets: dict[str, list[tuple[str, dict]]] = {}
    titles: dict[str, str] = {}
    for c in all_conds:
        klass, detail = classify(c, versions)
        buckets.setdefault(klass, []).append((c, detail))
        # Prefer the latest version's title.
        for _, v in reversed(versions):
            if c in v:
                titles[c] = v[c]["title"]
                break

    def title(c: str) -> str:
        return titles.get(c, "?")

    # ---- console summary ----
    print("\n=== SUMMARY ===", flush=True)
    for k in ("STABLE", "INTRODUCED", "REMOVED", "SINGLE-CHANGE", "MULTI-CHANGE", "ANOMALY"):
        if k in buckets:
            print(f"  {k:<14} {len(buckets[k])}", flush=True)

    print("\n=== Self-check (our hand-mapped conditions) ===", flush=True)
    for c in sorted(set(getattr(temporal, "MAPPED", {})) | set(getattr(temporal, "TEXT_CHANGES", {}))):
        klass = next((k for k, items in buckets.items() if any(x[0] == c for x in items)), "?")
        print(f"  Condition {c}{already_mapped(c)} -> detected {klass}", flush=True)

    # ---- markdown report ----
    lines: list[str] = []
    lines.append("# Condition change-map (Ofgem electricity supply SLCs)\n")
    lines.append("_Generated by `src/detect_changes.py` — a curation aid for choosing which "
                 "conditions to map for temporal awareness. Not part of the serving path._\n")
    lines.append("## Held snapshots\n")
    for d, v in versions:
        lines.append(f"- **{d.isoformat()}** — {len(v)} conditions")
    lines.append("\nIntervals compared:\n")
    for iv in intervals:
        lines.append(f"- {iv}")
    lines.append(
        "\n> **Caveat:** a snapshot diff only sees the ENDPOINTS of an interval. "
        "**SINGLE-CHANGE** = changed once *between* snapshots and is a *candidate* to confirm "
        "against Ofgem's modification history (as done for Condition 28); **MULTI-CHANGE** = "
        "changed in ≥ 2 intervals and is *confirmed* volatile. Resolution is only as fine "
        "as the snapshots held — ingest more consolidations to sharpen it.\n"
    )

    counts = " · ".join(f"{k} {len(buckets[k])}" for k in
                        ("STABLE", "INTRODUCED", "REMOVED", "SINGLE-CHANGE", "MULTI-CHANGE", "ANOMALY")
                        if k in buckets)
    lines.append(f"## Summary\n\n{counts}\n")

    def table(items, cols_fn, header):
        rows = [header, "|".join(["---"] * header.count("|") or ["---"])]
        # rebuild separator to match header column count
        ncol = header.count("|") + 1
        rows[1] = "|".join(["---"] * ncol)
        for c, detail in items:
            rows.append(cols_fn(c, detail))
        return "\n".join(rows) + "\n"

    # SINGLE-CHANGE — the text-change candidates, biggest change first per interval.
    sc = buckets.get("SINGLE-CHANGE", [])
    lines.append("## Text-change CANDIDATES (single-interval) — verify before mapping\n")
    lines.append("Sorted by change size (smallest similarity = biggest text change). "
                 "`sims` = similarity per interval; the changed interval is where it dropped.\n")
    sc_sorted = sorted(sc, key=lambda x: min(x[1]["sims"]))
    lines.append("| Cond | Title | changed in | sims | chars (per snapshot) |")
    lines.append("|---|---|---|---|---|")
    for c, d in sc_sorted:
        chg = ", ".join(f"I{i}" for i in d["changed_intervals"])
        lines.append(f"| {c}{already_mapped(c)} | {title(c)} | {chg} | {d['sims']} | {d['chars']} |")
    lines.append("")

    # INTRODUCED — existence-boundary candidates.
    intro = buckets.get("INTRODUCED", [])
    lines.append("## Existence-boundary CANDIDATES (introduced)\n")
    lines.append("| Cond | Title | introduced in interval |")
    lines.append("|---|---|---|")
    for c, d in sorted(intro, key=lambda x: x[1]["interval"]):
        lines.append(f"| {c}{already_mapped(c)} | {title(c)} | I{d['interval']} ({intervals[d['interval']-1]}) |")
    lines.append("")

    # MULTI-CHANGE — volatile, avoid for clean gap-free demos.
    mc = buckets.get("MULTI-CHANGE", [])
    lines.append("## Volatile (multi-interval change) — AVOID unless holding every version\n")
    lines.append("| Cond | Title | changed in | sims |")
    lines.append("|---|---|---|---|")
    for c, d in sorted(mc, key=lambda x: title(x[0])):
        chg = ", ".join(f"I{i}" for i in d["changed_intervals"])
        lines.append(f"| {c} | {title(c)} | {chg} | {d['sims']} |")
    lines.append("")

    # REMOVED / ANOMALY for completeness.
    for k, hdr in (("REMOVED", "Removed / became “Not used”"),
                   ("ANOMALY", "Anomalies (non-monotonic presence — inspect)")):
        items = buckets.get(k, [])
        if items:
            lines.append(f"## {hdr}\n")
            for c, d in items:
                lines.append(f"- **{c}** {title(c)} — {d}")
            lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote report -> {REPORT.relative_to(ROOT)}", flush=True)
    print("Top text-change candidates (verify mod-history before mapping):", flush=True)
    for c, d in sc_sorted[:12]:
        print(f"  {c:<5} {title(c)[:44]:<44} changed I{d['changed_intervals']} sims={d['sims']}{already_mapped(c)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
