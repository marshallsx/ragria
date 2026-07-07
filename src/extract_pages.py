"""
Phase 2 · Stage 1 — Extract PDF pages to a cache file.

Extracts every page of the source PDF as raw text (no cleaning) using pypdf,
and writes one JSON record per page to a JSONL cache. Downstream stages
(chunking, embedding) read this cache instead of re-parsing the 611-page PDF,
which is slow. Run this ONCE; re-run only if the source PDF changes.

Usage:
    venv/bin/python src/extract_pages.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from pypdf import PdfReader

# --- Paths (relative to project root) ---
ROOT = Path(__file__).resolve().parent.parent
SRC_PDF = ROOT / "data" / "raw" / "electricity-supply-slc-consolidated-2025-08.pdf"
OUT_DIR = ROOT / "data" / "interim"
OUT_FILE = OUT_DIR / "slc_pages.jsonl"


def main() -> int:
    if not SRC_PDF.exists():
        print(f"ERROR: source PDF not found: {SRC_PDF}", flush=True)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {SRC_PDF.name}", flush=True)
    t0 = time.time()
    reader = PdfReader(str(SRC_PDF))
    n_pages = len(reader.pages)
    print(f"Pages to extract: {n_pages}", flush=True)

    # Write atomically: build a temp file, then rename over the target.
    tmp = OUT_FILE.with_suffix(".jsonl.tmp")
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

    tmp.replace(OUT_FILE)
    dt = time.time() - t0
    size_mb = OUT_FILE.stat().st_size / 1_048_576

    print("--- DONE ---", flush=True)
    print(f"Wrote {n_pages} page records to {OUT_FILE.relative_to(ROOT)}", flush=True)
    print(f"Output size: {size_mb:.2f} MB", flush=True)
    print(f"Empty/blank pages: {empty_pages}", flush=True)
    print(f"Elapsed: {dt:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
