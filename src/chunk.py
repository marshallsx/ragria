"""
Phase 2 · Stage 2 — Chunk the cached pages into retrieval units.

Reads the page cache (data/interim/slc_pages.jsonl), parses it into Conditions
(the natural legal unit of the licence), and emits chunks with citation
metadata to data/interim/slc_chunks.jsonl. Does NOT embed — that's Stage 3.

Strategy (agreed): structure-aware by Condition (Option B), condition-level
citations. Long conditions are sub-split into overlapping word-windows sized to
stay under ChromaDB's default embedder limit (~256 tokens).

Usage:
    venv/bin/python src/chunk.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "interim" / "slc_pages.jsonl"
OUT = ROOT / "data" / "interim" / "slc_chunks.jsonl"

SOURCE_FILE = "electricity-supply-slc-consolidated-2025-08.pdf"
DOC_TITLE = "Electricity Supply Standard Licence Conditions (consolidated to 1 August 2025)"

BODY_START_PAGE = 7          # cover=1, ToC=2..6
TARGET_WORDS = 175           # ~ under the 256-token embedder cap
OVERLAP_WORDS = 25

# Ref allows multi-letter suffixes (e.g. 21BA, 19AA, 28AD) and dotted forms (12.A).
# The capital 'Condition' anchor + '.'/':' separator already excludes inline refs
# (which are lowercase 'condition ...') and sub-paragraph refs (no space after sep).
COND = re.compile(r"^Condition\s+(\d+[A-Z]{0,3}(?:\.[A-Z])?)[.:]\s+(.+)")
SECTION = re.compile(r"^(SECTION\s+[A-Z][0-9]?):\s*(.*)")


def is_boiler(line: str) -> bool:
    """True for repeated header/footer noise we don't want in chunks."""
    l = line.strip()
    if not l:
        return True
    if l.startswith("Note: Consolidated conditions"):
        return True
    if "Licence: Standard Conditions - Consolidated" in l:
        return True
    if l in ("Electricity", "suppliers"):
        return True
    if re.fullmatch(r"\d{1,3}", l):        # standalone page number
        return True
    return False


def load_pages() -> list[dict]:
    recs = [json.loads(x) for x in CACHE.read_text(encoding="utf-8").splitlines()]
    return sorted(recs, key=lambda r: r["page"])


def parse_conditions(pages: list[dict]) -> list[dict]:
    """Walk body lines, grouping text under the current Condition."""
    conditions: list[dict] = []
    cur = None
    section = None

    for rec in pages:
        if rec["page"] < BODY_START_PAGE:
            continue
        page = rec["page"]
        for raw_line in rec["text"].split("\n"):
            line = raw_line.strip()
            if is_boiler(line):
                continue

            s = SECTION.match(line)
            if s:
                section = s.group(1)        # e.g. "SECTION A"
                continue

            m = COND.match(line)
            if m:
                # New condition begins — close the previous one.
                cur = {
                    "condition": m.group(1),
                    "condition_title": m.group(2).strip(),
                    "section": section,
                    "page_start": page,
                    "page_end": page,
                    "lines": [],
                }
                conditions.append(cur)
                continue

            if cur is not None:
                cur["lines"].append(line)
                cur["page_end"] = page

    return conditions


def window(words: list[str], size: int, overlap: int):
    """Yield overlapping windows of `words`."""
    if len(words) <= size:
        yield words
        return
    step = size - overlap
    i = 0
    while i < len(words):
        yield words[i : i + size]
        if i + size >= len(words):
            break
        i += step


def build_chunks(conditions: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for c in conditions:
        text = " ".join(c["lines"]).strip()
        # Even "Not used" conditions keep a stub so the condition is queryable.
        body = text if text else f"Condition {c['condition']}: {c['condition_title']}"
        words = body.split()
        for idx, w in enumerate(window(words, TARGET_WORDS, OVERLAP_WORDS)):
            chunk_text = " ".join(w)
            chunks.append({
                "id": f"cond{c['condition']}_{idx}",
                "text": chunk_text,
                "metadata": {
                    "source": SOURCE_FILE,
                    "doc_title": DOC_TITLE,
                    "section": c["section"] or "",
                    "condition": c["condition"],
                    "condition_title": c["condition_title"],
                    "page_start": c["page_start"],
                    "page_end": c["page_end"],
                    "chunk_index": idx,
                    "n_words": len(w),
                },
            })
    return chunks


def main() -> int:
    if not CACHE.exists():
        print(f"ERROR: cache not found: {CACHE}. Run src/extract_pages.py first.", flush=True)
        return 1

    pages = load_pages()
    conditions = parse_conditions(pages)
    chunks = build_chunks(conditions)

    with OUT.open("w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    # --- Stats for the verify gate ---
    per_cond: dict[str, int] = {}
    for ch in chunks:
        per_cond[ch["metadata"]["condition"]] = per_cond.get(ch["metadata"]["condition"], 0) + 1
    word_counts = [ch["metadata"]["n_words"] for ch in chunks]
    multi = {k: v for k, v in per_cond.items() if v > 1}

    print("--- CHUNKING DONE ---", flush=True)
    print(f"conditions parsed : {len(conditions)}", flush=True)
    print(f"chunks written    : {len(chunks)} -> {OUT.relative_to(ROOT)}", flush=True)
    print(f"words/chunk       : min={min(word_counts)} max={max(word_counts)} "
          f"mean={sum(word_counts)//len(word_counts)}", flush=True)
    print(f"conditions that sub-split (>1 chunk): {len(multi)}", flush=True)
    top = sorted(multi.items(), key=lambda kv: kv[1], reverse=True)[:5]
    print(f"  biggest: {top}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
