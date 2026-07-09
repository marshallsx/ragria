"""A/B: MiniLM (current) vs bge-small (ONNX) on retrieval quality over the eval answer-cases.
Isolates the embedder's effect (vector-only) and its practical impact (hybrid ± synonyms).

Hardened for a 4 GB / 1.8 GB-WSL box (this is a rebuild of a version that OOM-crashed):

  1. TWO memory-isolated phases. The embedding phase loads ONLY the ONNX model + chunk
     texts — it does NOT touch Chroma or build the BM25 index. Those load only in the
     compare phase, after `texts` is freed. So no single moment holds model + corpus
     vectors + Chroma collection + BM25 all at once (that combination is what got killed).
  2. RESUMABLE, ATOMIC checkpoint. Vectors are flushed to disk every few batches via
     tmp-file + os.replace. A crash resumes from the last flush instead of restarting at 0.
     A *completed* checkpoint skips embedding entirely, so a crash during the compare phase
     never re-embeds.
  3. Small batches + capped ONNX threads to keep the peak resident set down.
  4. Single-process embedding (parallel=1) — no worker fork storm.

Tunables (env): BGE_BATCH (default 32), BGE_THREADS (default 2), BGE_FLUSH batches/flush (2).

Run in the BACKGROUND writing a log, e.g.:
    venv/bin/python evals/embedder_ab.py > evals/embedder_ab.log 2>&1 &
    tail -f evals/embedder_ab.log
Nothing here runs on import; it only runs under `if __name__ == "__main__"`.
"""
import gc
import json
import os
import sys
import traceback
from pathlib import Path

# --- thread caps MUST be set before numpy / onnxruntime import ---
THREADS = os.environ.get("BGE_THREADS", "2")
os.environ.setdefault("OMP_NUM_THREADS", THREADS)
os.environ.setdefault("OPENBLAS_NUM_THREADS", THREADS)
os.environ.setdefault("MKL_NUM_THREADS", THREADS)
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np  # noqa: E402
import yaml  # noqa: E402

ROOT = Path("/home/marshallsx/projects/ragria")
sys.path.insert(0, str(ROOT))
from src import versions  # noqa: E402  (cheap import — no model/collection loaded)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH = int(os.environ.get("BGE_BATCH", "32"))
FLUSH_EVERY = int(os.environ.get("BGE_FLUSH", "2"))  # flush checkpoint every N batches
CUR = versions.CURRENT_LABEL

CHUNKS_FILE = ROOT / "data/interim/slc_chunks.jsonl"
CKPT_DIR = ROOT / "data/interim/bge_ab_ckpt"      # gitignored (data/ is ignored); durable
VECS_F = CKPT_DIR / "vecs.npy"                     # raw (unnormalized) float32 [k, dim]
IDS_F = CKPT_DIR / "ids.json"                      # current-version chunk ids, in order
PROG_F = CKPT_DIR / "progress.json"                # {"n", "total", "complete", "model"}


def log(msg: str) -> None:
    print(msg, flush=True)


def _atomic_write_bytes(path: Path, write_fn) -> None:
    """Write via a temp sibling + os.replace so a crash mid-write can't corrupt the file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        write_fn(fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _save_checkpoint(vecs_list, total: int, complete: bool) -> None:
    arr = np.asarray(vecs_list, dtype=np.float32)
    _atomic_write_bytes(VECS_F, lambda fh: np.save(fh, arr))
    prog = {"n": len(vecs_list), "total": total, "complete": complete, "model": MODEL_NAME}
    _atomic_write_bytes(PROG_F, lambda fh: fh.write(json.dumps(prog).encode()))


def _load_current_chunks():
    chunks = [json.loads(l) for l in CHUNKS_FILE.read_text(encoding="utf-8").splitlines()]
    cur = [c for c in chunks if c["metadata"]["version_label"] == CUR]
    return [c["id"] for c in cur], [c["text"] for c in cur]


def embed_corpus(ids, texts):
    """Return raw (unnormalized) corpus vectors, resuming from checkpoint if present.
    Loads ONLY the ONNX model here — no Chroma, no BM25 — to keep peak memory low."""
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(texts)

    # ---- resume / validate checkpoint ----
    start = 0
    vecs_list = []
    if PROG_F.exists() and VECS_F.exists() and IDS_F.exists():
        prog = json.loads(PROG_F.read_text())
        saved_ids = json.loads(IDS_F.read_text())
        if saved_ids == ids and prog.get("model") == MODEL_NAME:
            saved = np.load(VECS_F)
            if prog.get("complete") and saved.shape[0] == total:
                log(f"[1/3] checkpoint COMPLETE ({total} vecs) — skipping embedding.")
                return saved.astype(np.float32)
            start = int(prog.get("n", saved.shape[0]))
            start = min(start, saved.shape[0])          # never trust n > rows actually on disk
            vecs_list = [row for row in saved[:start]]
            log(f"[1/3] resuming from checkpoint at {start}/{total}.")
        else:
            log("[1/3] checkpoint mismatch (ids/model changed) — restarting embedding from 0.")
    if not vecs_list:
        _atomic_write_bytes(IDS_F, lambda fh: fh.write(json.dumps(ids).encode()))

    # ---- embed remaining, single-process, batched, incremental flush ----
    from fastembed import TextEmbedding
    log(f"[1/3] loading {MODEL_NAME} (threads={THREADS}) + embedding {total} chunks, "
        f"batch={BATCH}, flush every {FLUSH_EVERY} batches...")
    emb = TextEmbedding(model_name=MODEL_NAME, threads=int(THREADS))

    batch_no = 0
    for i in range(start, total, BATCH):
        vecs_list.extend(emb.embed(texts[i:i + BATCH], parallel=1))  # parallel=1 => no forks
        done = min(i + BATCH, total)
        batch_no += 1
        if batch_no % FLUSH_EVERY == 0 or done == total:
            _save_checkpoint(vecs_list, total, complete=(done == total))
            log(f"    embedded {done}/{total}  (checkpointed)")
    del emb
    gc.collect()
    return np.asarray(vecs_list, dtype=np.float32)


def run_ab(ids, cvecs_raw):
    """Compare phase: NOW load Chroma + BM25 (heavy), with `texts` already freed.
    Re-instantiates the ONNX model only for the handful of query embeddings."""
    from fastembed import TextEmbedding
    from src import rag

    CAND_N, TOPK = rag.CAND_N, rag.TOP_K
    coll = rag.get_collection()
    bm25, bm25_ids, cbi = rag.get_bm25()
    cond_of = {i: cbi[i]["metadata"]["condition"] for i in cbi}

    def norm(m):
        return m / (np.linalg.norm(m, axis=-1, keepdims=True) + 1e-9)

    cvecs = norm(cvecs_raw)
    emb = TextEmbedding(model_name=MODEL_NAME, threads=int(THREADS))
    log("[2/3] corpus vectors loaded + Chroma/BM25 ready. running retrieval A/B...")

    def bge_vec_ids(q, n):
        qv = norm(np.array(list(emb.query_embed([q], parallel=1))))[0]
        order = np.argsort(-(cvecs @ qv))[:n]
        return [ids[i] for i in order]

    def minilm_vec_ids(q, n):
        return [h["id"] for h in rag.vector_retrieve(q, n, coll)]

    def bm25_for(q, n, synonyms):
        toks = rag.expand_query(q) if synonyms else rag.tokenize(q)
        sc = bm25.get_scores(toks)
        top = sorted(range(len(bm25_ids)), key=lambda i: sc[i], reverse=True)[:n]
        return [bm25_ids[i] for i in top]

    def cond_rank(id_list, expected):
        seen = []
        for i in id_list:
            c = cond_of.get(i)
            if c and c not in seen:
                seen.append(c)
        for r, c in enumerate(seen, 1):
            if c in expected:
                return r
        return None

    METHODS = {
        "MiniLM vector":       lambda q: minilm_vec_ids(q, 40),
        "bge    vector":       lambda q: bge_vec_ids(q, 40),
        "MiniLM hybrid+syn":   lambda q: rag.rrf([minilm_vec_ids(q, CAND_N), bm25_for(q, CAND_N, True)]),
        "bge    hybrid+syn":   lambda q: rag.rrf([bge_vec_ids(q, CAND_N), bm25_for(q, CAND_N, True)]),
        "bge    hybrid NOsyn": lambda q: rag.rrf([bge_vec_ids(q, CAND_N), bm25_for(q, CAND_N, False)]),
    }

    cases = [c for c in yaml.safe_load((ROOT / "evals/cases.yaml").read_text())
             if c["expected"] == "answer"]
    ranks = {m: [] for m in METHODS}
    hard = {"O4": "21BA", "P1": "27", "P3": "26", "S3": "26"}
    hard_ranks = {m: {} for m in METHODS}

    for c in cases:
        exp = set(c["expect_conditions"])
        for m, fn in METHODS.items():
            r = cond_rank(fn(c["question"]), exp)
            ranks[m].append(r)
            if c["id"] in hard:
                hard_ranks[m][c["id"]] = r

    n = len(cases)

    def rec(rs, k):
        return sum(1 for r in rs if r and r <= k)

    def mr(rs):
        hits = [r for r in rs if r]
        return round(sum(hits) / len(hits), 2) if hits else None

    log(f"\n[3/3] === Retrieval A/B over {n} answer-cases (rank of first expected condition) ===")
    log(f"{'method':<20} {'recall@1':<9} {'recall@3':<9} {'recall@6':<9} {'mean_rank':<9} misses(>6 or none)")
    for m in METHODS:
        rs = ranks[m]
        miss = [cases[i]['id'] for i, r in enumerate(rs) if not r or r > TOPK]
        log(f"{m:<20} {rec(rs,1):>3}/{n:<5} {rec(rs,3):>3}/{n:<5} {rec(rs,6):>3}/{n:<5} {str(mr(rs)):<9} {miss}")

    log("\n=== Illustrative hard cases (rank of expected condition; None = not in list) ===")
    log(f"{'method':<20} " + " ".join(f"{cid}({hard[cid]})" for cid in hard))
    for m in METHODS:
        log(f"{m:<20} " + " ".join(f"{str(hard_ranks[m].get(cid)):<8}" for cid in hard))
    log("\nDONE.")


def main():
    ids, texts = _load_current_chunks()
    cvecs_raw = embed_corpus(ids, texts)
    del texts                      # free corpus text before loading Chroma + BM25
    gc.collect()
    run_ab(ids, cvecs_raw)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        sys.exit(1)
