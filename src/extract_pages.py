"""
Phase 2 · Stage 1 — Extract PDF pages to per-version cache files.

Extracts every page of each held consolidation (see src/versions.py) as raw text
(no cleaning) using pypdf, writing one JSON record per page to a per-version JSONL
cache. Downstream stages (chunking, embedding) read these caches instead of
re-parsing the multi-hundred-page PDFs, which is slow. Run this ONCE; re-run only
if a source PDF changes or a version is added.

Usage:
    venv/bin/python src/extract_pages.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from pypdf import PdfReader

try:  # works both as `src.*` and as `python src/extract_pages.py`
    from src import versions
except ImportError:
    import versions

# --- Paths (relative to project root) ---
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "interim"


def extract_version(v: dict) -> int:
    src_pdf = RAW_DIR / v["pdf"]
    out_file = OUT_DIR / v["cache"]
    if not src_pdf.exists():
        print(f"ERROR: source PDF not found: {src_pdf}", flush=True)
        return 0

    print(f"\n=== {v['label']} :: {src_pdf.name} ===", flush=True)
    t0 = time.time()
    reader = PdfReader(str(src_pdf))
    n_pages = len(reader.pages)
    print(f"Pages to extract: {n_pages}", flush=True)

    # Write atomically: build a temp file, then rename over the target.
    tmp = out_file.with_suffix(".jsonl.tmp")
    empty_pages = 0
    with tmp.open("w", encoding="utf-8") as f:
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if not text.strip():
                empty_pages += 1
            rec = {"page": i + 1, "text": text}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if (i + 1) % 100 == 0:
                print(f"  ...{i + 1}/{n_pages} pages", flush=True)

    tmp.replace(out_file)
    dt = time.time() - t0
    size_mb = out_file.stat().st_size / 1_048_576
    print(f"Wrote {n_pages} page records to {out_file.relative_to(ROOT)} "
          f"({size_mb:.2f} MB, {empty_pages} empty, {dt:.1f}s)", flush=True)
    return n_pages


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for v in versions.VERSIONS:
        total += extract_version(v)
    print("\n--- DONE ---", flush=True)
    print(f"Extracted {len(versions.VERSIONS)} version(s), {total} pages total.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
