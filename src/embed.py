"""
Phase 2 · Stage 3 — Embed chunks and store them in ChromaDB.

Reads data/interim/slc_chunks.jsonl and loads every chunk into a persistent
ChromaDB collection, using Chroma's built-in default embedder
(all-MiniLM-L6-v2 via onnxruntime — no PyTorch, no separate model download step
beyond the first-run model fetch). The store persists to ./chroma (gitignored).

Idempotent: the collection is deleted and rebuilt on each run, so re-running
never produces duplicates.

Usage:
    venv/bin/python src/embed.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "interim" / "slc_chunks.jsonl"
STORE = ROOT / "chroma"
COLLECTION = "ofgem_slc_electricity"
BATCH = 200


def main() -> int:
    if not CHUNKS.exists():
        print(f"ERROR: chunks not found: {CHUNKS}. Run src/chunk.py first.", flush=True)
        return 1

    chunks = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines()]
    print(f"chunks to embed: {len(chunks)}", flush=True)

    client = chromadb.PersistentClient(path=str(STORE))

    # Reset for idempotency.
    try:
        client.delete_collection(COLLECTION)
        print(f"(reset) deleted existing collection '{COLLECTION}'", flush=True)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION)  # uses default embedder

    # NOTE (Phase 5): we tried prepending the condition title to the embedded text
    # to fix the O4 false refusal ("maximum back-billing period" not retrieving
    # Condition 21BA "Backbilling"). Measured result: 21BA moved from absent-in-top-15
    # to rank 18 — insufficient, so reverted. The keyword "Backbilling" maps to exactly
    # 21BA's chunks, so the real fix is hybrid keyword+vector retrieval (see evals/report.md).
    t0 = time.time()
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        coll.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
        print(f"  embedded {min(i + BATCH, len(chunks))}/{len(chunks)}", flush=True)

    dt = time.time() - t0
    print("--- EMBEDDING DONE ---", flush=True)
    print(f"collection '{COLLECTION}' count: {coll.count()}", flush=True)
    print(f"store path: {STORE.relative_to(ROOT)}/", flush=True)
    print(f"elapsed: {dt:.1f}s", flush=True)

    # --- tiny end-to-end smoke test ---
    q = "Can a supplier back-bill a domestic customer for more than 12 months?"
    res = coll.query(query_texts=[q], n_results=3)
    print(f"\nsmoke query: {q!r}", flush=True)
    for doc_id, meta, dist in zip(res["ids"][0], res["metadatas"][0], res["distances"][0]):
        print(f"  {doc_id} | Cond {meta['condition']} \"{meta['condition_title']}\" "
              f"(pp{meta['page_start']}-{meta['page_end']}) | dist={dist:.3f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
