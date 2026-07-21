"""
Phase 6 — Version history / "what changed" view (presentation helper).

For a mapped condition + an as-of date, produce the data the UI needs to render a
timeline and a word-level diff of what changed. Reads the version-tagged chunks
(`slc_chunks.jsonl` — the deployed artefact, so no dependency on the gitignored page
caches) and reconstructs each held version's full condition text by de-overlapping the
25-word chunk overlap.

Two kinds, matching temporal.py:
  * text-change (TEXT_CHANGES) → timeline + a word-level diff (added green / removed red)
  * introduced  (MAPPED)       → timeline + "did/didn't exist as of the date"
"""
from __future__ import annotations

import difflib
import json
from datetime import date
from pathlib import Path

try:  # works as `src.history` (app/evals) and `import history` (python src/*)
    from src import temporal, versions
except ImportError:
    import temporal, versions

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = ROOT / "data" / "interim" / "slc_chunks.jsonl"

MAX_DIFF_WORDS = 140   # cap the rendered diff so a huge change (e.g. 28) doesn't flood the panel
CONTEXT_WORDS = 6      # words of unchanged context kept either side of a change

_TEXTS: dict[tuple[str, str], str] | None = None  # (version_label, condition) -> full text


def _dedupe_join(texts: list[str]) -> str:
    """Reconstruct a condition's full text from its overlapping chunks: for each next
    chunk, drop the longest prefix that duplicates the current tail (the 25-word overlap)."""
    if not texts:
        return ""
    result = texts[0].split()
    for t in texts[1:]:
        words = t.split()
        k = 0
        for cand in range(min(len(result), len(words)), 0, -1):
            if result[-cand:] == words[:cand]:
                k = cand
                break
        result.extend(words[k:])
    return " ".join(result)


def _load() -> dict[tuple[str, str], str]:
    global _TEXTS
    if _TEXTS is None:
        by: dict[tuple[str, str], list[tuple[int, str]]] = {}
        for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            m = c["metadata"]
            by.setdefault((m["version_label"], m["condition"]), []).append((m["chunk_index"], c["text"]))
        _TEXTS = {key: _dedupe_join([t for _, t in sorted(items)]) for key, items in by.items()}
    return _TEXTS


def _full_text(version_label: str, condition: str) -> str:
    return _load().get((version_label, condition), "")


def _diff(before: str, after: str) -> tuple[list[dict], bool]:
    """Word-level diff → segments [{type: context|add|del|gap, text}], changed regions
    only (long unchanged runs collapse to a '…' gap), capped at MAX_DIFF_WORDS."""
    a, b = before.split(), after.split()
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    segs: list[dict] = []
    budget = MAX_DIFF_WORDS
    truncated = False
    for idx, (tag, i1, i2, j1, j2) in enumerate(ops):
        if budget <= 0:
            truncated = True
            break
        if tag == "equal":
            run = a[i1:i2]
            prev_chg, next_chg = idx > 0, idx < len(ops) - 1
            if len(run) <= 2 * CONTEXT_WORDS:
                if prev_chg or next_chg:
                    segs.append({"type": "context", "text": " ".join(run)})
            else:
                if prev_chg:
                    segs.append({"type": "context", "text": " ".join(run[:CONTEXT_WORDS])})
                segs.append({"type": "gap", "text": "…"})
                if next_chg:
                    segs.append({"type": "context", "text": " ".join(run[-CONTEXT_WORDS:])})
        elif tag in ("delete", "replace"):
            w = a[i1:i2][:budget]
            segs.append({"type": "del", "text": " ".join(w)})
            budget -= len(w)
        if tag in ("insert", "replace") and budget > 0:
            w = b[j1:j2][:budget]
            segs.append({"type": "add", "text": " ".join(w)})
            budget -= len(w)
    # tidy: drop leading/trailing gaps
    while segs and segs[0]["type"] == "gap":
        segs.pop(0)
    while segs and segs[-1]["type"] == "gap":
        segs.pop()
    return segs, truncated


def view(condition: str, as_of: date) -> dict | None:
    """History view for a mapped condition, or None if the condition isn't mapped."""
    if condition in temporal.TEXT_CHANGES:
        return _text_change_view(condition, as_of)
    if condition in temporal.MAPPED:
        return _introduced_view(condition, as_of)
    return None


def _served_index(segs: list[dict], as_of: date) -> int:
    """Index of the segment in force as of `as_of`, clamped to the ends (before the first
    segment → 0; on/after the last → the last)."""
    for i, s in enumerate(segs):
        if as_of >= s["start"] and (s["end"] is None or as_of < s["end"]):
            return i
    return 0 if as_of < segs[0]["start"] else len(segs) - 1


def _bracketed_change(segs: list[dict], as_of: date) -> tuple[int | None, int]:
    """(change_seg, served) — the change to DESCRIBE for a reader at `as_of`, and the segment
    they are being served. The described change is the one that BRACKETS the served version: the
    change that produced it (served-1 → served) if they are on/after a change, else the first
    UPCOMING change (0 → 1). Returning the segment index on the NEW side of that change means the
    diff (segs[change-1] → segs[change]) always covers exactly the change the label names — so a
    condition that changed more than once no longer mislabels one change's diff with another's
    date (the bug Condition 28 exposed once it gained a third segment)."""
    served = _served_index(segs, as_of)
    if served >= 1:
        return served, served                       # change that produced the served version
    return (1 if len(segs) > 1 else None), served   # before every change → the first upcoming one


def _text_change_view(cond: str, as_of: date) -> dict:
    tc = temporal.TEXT_CHANGES[cond]
    segs = tc["segments"]
    intro = tc.get("introduced")
    markers = [
        {"date": temporal.fmt(s["start"]),
         "label": ("introduced" if i == 0 and intro else "original text" if i == 0 else "text changed"),
         "note": s["note"]}
        for i, s in enumerate(segs)
    ]
    change_seg, served = _bracketed_change(segs, as_of)
    if change_seg is not None:
        change_date = segs[change_seg]["start"]
        before = _full_text(segs[change_seg - 1]["version"], cond)
        after = _full_text(segs[change_seg]["version"], cond)
        diff, truncated = _diff(before, after)
    else:
        change_date, diff, truncated = None, [], False
    return {
        "condition": cond, "title": tc["title"], "kind": "text-change",
        "as_of": temporal.fmt(as_of),
        "change_date": temporal.fmt(change_date) if change_date else None,
        "on_after": served >= 1,
        "showing": temporal.fmt(segs[served]["start"]),  # the version the reader is served
        "markers": markers, "diff": diff, "diff_truncated": truncated,
    }


def _introduced_view(cond: str, as_of: date) -> dict:
    m = temporal.MAPPED[cond]
    return {
        "condition": cond, "title": m["title"], "kind": "introduced",
        "as_of": temporal.fmt(as_of),
        "introduced": temporal.fmt(m["introduced"]),
        "existed": as_of >= m["introduced"],
        "markers": [
            {"date": "earlier", "label": "did not exist", "note": "not in the licence"},
            {"date": temporal.fmt(m["introduced"]), "label": "introduced", "note": m["title"]},
        ],
    }


def _side_by_side(old: str, new: str) -> tuple[list[dict], list[dict]]:
    """Full-text word-level diff → (left_segments, right_segments). Left carries the OLD text
    with deletions marked; right carries the NEW text with additions marked; unchanged text
    ('eq') appears on both. For a side-by-side compare view (whole text, not just changed bits)."""
    a, b = old.split(), new.split()
    left, right = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            left.append({"type": "eq", "text": " ".join(a[i1:i2])})
            right.append({"type": "eq", "text": " ".join(b[j1:j2])})
        elif tag == "delete":
            left.append({"type": "del", "text": " ".join(a[i1:i2])})
        elif tag == "insert":
            right.append({"type": "add", "text": " ".join(b[j1:j2])})
        elif tag == "replace":
            left.append({"type": "del", "text": " ".join(a[i1:i2])})
            right.append({"type": "add", "text": " ".join(b[j1:j2])})
    return left, right


def comparable() -> list[tuple[str, str]]:
    """(condition, title) for the text-change conditions that have a two-version compare."""
    return [(c, tc["title"]) for c, tc in temporal.TEXT_CHANGES.items()]


def compare(condition: str, as_of: date | None = None) -> dict | None:
    """Side-by-side of the two versions bracketing ONE change — the same change the inline panel
    describes for `as_of`, so the drill-down matches it. With no `as_of` (back-compat) it brackets
    the most recent change."""
    tc = temporal.TEXT_CHANGES.get(condition)
    if tc is None:
        return None
    segs = tc["segments"]
    if as_of is not None:
        change_seg, _ = _bracketed_change(segs, as_of)
    else:
        change_seg = len(segs) - 1 if len(segs) > 1 else None
    if change_seg is None:
        return None
    old_seg, new_seg = segs[change_seg - 1], segs[change_seg]
    left_segs, right_segs = _side_by_side(
        _full_text(old_seg["version"], condition), _full_text(new_seg["version"], condition)
    )
    change = new_seg["start"]
    v_old, v_new = versions.BY_LABEL[old_seg["version"]], versions.BY_LABEL[new_seg["version"]]
    right_in_force = (f"from {temporal.fmt(change)} (current)" if new_seg["end"] is None
                      else f"{temporal.fmt(change)} – {temporal.fmt(new_seg['end'])}")
    return {
        "condition": condition, "title": tc["title"], "change_date": temporal.fmt(change),
        "note": new_seg["note"],
        "left": {
            "in_force": f"{temporal.fmt(old_seg['start'])} – {temporal.fmt(old_seg['end'])}",
            "consolidation": temporal.fmt(v_old["date"]), "segs": left_segs,
        },
        "right": {
            "in_force": right_in_force,
            "consolidation": temporal.fmt(v_new["date"]), "segs": right_segs,
        },
    }


def views_for(citations: list[dict], as_of: date, limit: int = 2) -> list[dict]:
    """History views for the mapped conditions among the answer's citations (deduped)."""
    out, seen = [], set()
    for c in citations:
        cond = c.get("condition", "")
        if cond in seen:
            continue
        v = view(cond, as_of)
        if v:
            seen.add(cond)
            out.append(v)
        if len(out) >= limit:
            break
    return out
