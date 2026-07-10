"""
Phase 3 — Retrieval + grounded generation.

query -> retrieve top-k chunks from ChromaDB -> build a grounded prompt ->
call Claude (Opus 4.8, adaptive thinking, structured output) -> return a
grounded answer with condition-level citations, or an explicit refusal.

`answer_question()` is the single entry point the Streamlit UI (Phase 4) calls.

Design decisions (agreed):
- top_k = 6 (small chunks + a moderately discriminating embedder → favour recall)
- Refusal is LLM-judged (primary), with a coarse distance backstop that skips the
  API call on obviously out-of-scope questions.
- Structured JSON output (guaranteed-parseable → trivial UI wiring).
- Model is a single constant so Phase 5 evals can A/B it.

Usage (CLI smoke test):
    venv/bin/python src/rag.py "Can a supplier back-bill a customer beyond 12 months?"
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import anthropic
import chromadb
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

try:  # works both as `src.rag` (app/evals) and `python src/rag.py`
    from src import temporal, versions, history
except ImportError:
    import temporal, versions, history

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "chroma"
COLLECTION = "ofgem_slc_electricity"

MODEL = "claude-opus-4-8"
TOP_K = 6
CAND_N = 10          # candidates pulled from each retriever before fusion
RRF_K = 60           # reciprocal-rank-fusion constant
TITLE_WEIGHT = 8     # BM25 field boost: repeat the condition title so a query that
                     # names a condition (e.g. "back-billing" → title "Backbilling")
                     # ranks it highly. Swept vs eval controls — 8 fixes O4, no regressions.
EXPAND_FULL_CAP = 8  # a hit on a small condition (≤ this many chunks) pulls the WHOLE
                     # condition; larger conditions fall back to ±1 neighbours (bounded)
LARGE_TOP_N = 2      # ALSO fully expand the top-N matched conditions even if large, so a
                     # peripheral match on a big condition (e.g. 27, 17 chunks) still serves
                     # its relevant part — the P1 false-refusal fix...
LARGE_MAX_CHUNKS = 30  # ...but never a monster (34=131, 1=68, 28AD=58 chunks) — those stay ±1
CHUNKS_FILE = ROOT / "data" / "interim" / "slc_chunks.jsonl"
# Coarse backstop only. The LLM makes the real refusal call; this just avoids an
# API round-trip when even the closest chunk is clearly unrelated.
# Verify-gate calibration: in-scope questions ran best-distance 0.71-0.95; an
# out-of-scope question was 1.07 — too close to separate cleanly, so the backstop
# stays lenient and the LLM handles the nuanced refusals. Revisit in Phase 5 evals.
DISTANCE_FLOOR = 1.6

load_dotenv(ROOT / ".env")

SYSTEM = """You are a regulatory research assistant for the Ofgem Electricity Supply \
Standard Licence Conditions. The current licence version and the as-of date are given in \
the user message.

You are given a user question and a set of numbered extracts retrieved from that \
document. Each extract is labelled with its Condition number, title, and page range.

Answer using only the information in the provided extracts:
- Do not use outside knowledge or general assumptions about energy regulation.
- If the extracts do not contain enough information to answer, do not guess. Set \
refused to true, leave answer empty, and in reason briefly say what was missing.
- When you answer, ground every statement in the extracts and cite the specific \
conditions you relied on. Do not add requirements that are not in the text.
- Keep the answer concise and factual.

Temporal awareness (dates):
- You are given an "As-of date", and for relevant conditions, when they were introduced \
or when their text changed.
- Answer as of that date. If a condition relevant to the question did NOT exist as of the \
as-of date, say so plainly and give its introduction date — do NOT present its current \
text as if it applied then.
- Some conditions had their TEXT changed on a date. The Temporal facts tell you which \
version's text was in force as of the as-of date and its effective range, and the \
retrieved extract for that condition is ALREADY that version's text. Answer from that \
extract, and state which consolidation/date you are relying on. Never present a later \
version's text as applying before its change date.
- If the user's question itself names a time period that straddles a condition's \
introduction or text-change date, do not pick a side: say it changed on that date and \
give BOTH the "before" and "after" states.
- When answering for a past date, make the date explicit in your answer.
- For a PAST as-of date, only make definite dated claims about conditions whose \
introduction/effective/change dates are given in the Temporal facts above. For any OTHER \
condition, do not assert it applied as of that date — omit it, or note its historic \
status as of that date is not confirmed.

Return your response in the required structured format."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "refused": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "condition": {"type": "string",
                                  "description": "Bare condition number only, e.g. 0A, 21BA, 28 — no 'Condition' prefix."},
                    "condition_title": {"type": "string"},
                    "pages": {"type": "string"},
                },
                "required": ["condition", "condition_title", "pages"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string"},
    },
    "required": ["refused", "answer", "citations", "reason"],
    "additionalProperties": False,
}


def get_collection():
    client = chromadb.PersistentClient(path=str(STORE))
    return client.get_collection(COLLECTION)


def get_client():
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from .env


# --- Hybrid retrieval: semantic (vector) + lexical (BM25), fused by RRF ---
#
# Vector search handles paraphrase but has vocabulary blind spots (O4: "maximum
# back-billing period" didn't retrieve 21BA "Backbilling"). BM25 matches literal
# terms, so it catches exactly those cases. Reciprocal Rank Fusion merges the two
# ranked lists by position, sidestepping their incompatible score scales.

_TOKEN = re.compile(r"[a-z0-9]+")
_BM25 = None  # module-level cache: (BM25Okapi, ids, chunk_by_id)

# Lay-language → licence-vocabulary aliases, added to the BM25 QUERY ONLY (never the corpus),
# so everyday phrasing reaches the right condition when the licence uses formal terms. Each key
# is a phrase to look for in the raw question; its tokens are appended to the query.
QUERY_ALIASES = {
    "cut off": ["disconnect", "disconnection"],
    "cutting off": ["disconnect", "disconnection"],
    "switch off": ["disconnect", "disconnection"],
    "unpaid bill": ["debt", "nonpayment", "arrears"],
    "not paid": ["debt", "nonpayment"],
    "extra help": ["priority", "services", "register"],
    "additional support": ["priority", "services", "register"],
    "vulnerable": ["priority", "services", "register"],
    "vulnerability": ["priority", "services", "register"],
    "change supplier": ["customer", "transfer"],
    "switching supplier": ["customer", "transfer"],
    "pay as you go": ["prepayment"],
}


def tokenize(text: str) -> list[str]:
    """Lowercase alnum tokens, plus a de-hyphenated join so 'back-billing' also
    yields 'backbilling' (matching the one-word title 'Backbilling')."""
    text = text.lower()
    toks = _TOKEN.findall(text)
    for m in re.finditer(r"([a-z0-9]+)-([a-z0-9]+)", text):
        toks.append(m.group(1) + m.group(2))
    return toks


def expand_query(question: str) -> list[str]:
    """Query tokens + lay→licence alias tokens (BM25 side only), so 'cutting off' reaches
    'disconnection' and 'extra help / vulnerable' reaches 'Priority Services Register'."""
    toks = tokenize(question)
    ql = question.lower()
    for phrase, extra in QUERY_ALIASES.items():
        if phrase in ql:
            toks.extend(extra)
    return toks


def get_bm25():
    """Build (once) an in-memory BM25 index over the CURRENT version's chunk *title + text*.
    Primary retrieval is over the current version only (historic text enters via the
    deliberate per-condition swap in expand_hits), so BM25 is scored over current chunks;
    chunk_by_id still holds ALL versions so the swap can fetch historic chunks by id."""
    global _BM25
    if _BM25 is None:
        chunks = [json.loads(l) for l in CHUNKS_FILE.read_text(encoding="utf-8").splitlines()]
        chunk_by_id = {c["id"]: c for c in chunks}
        current = [c for c in chunks if c["metadata"]["version_label"] == versions.CURRENT_LABEL]
        ids = [c["id"] for c in current]
        corpus = [
            tokenize((c["metadata"]["condition_title"] + " ") * TITLE_WEIGHT + c["text"])
            for c in current
        ]
        _BM25 = (BM25Okapi(corpus), ids, chunk_by_id)
    return _BM25


def vector_retrieve(question: str, n: int = CAND_N, coll=None) -> list[dict]:
    coll = coll or get_collection()
    # Restrict to the current version; historic text enters only via expand_hits' swap.
    res = coll.query(
        query_texts=[question], n_results=n,
        where={"version_label": versions.CURRENT_LABEL},
    )
    return [
        {"id": i, "text": d, "meta": m, "distance": dist}
        for i, d, m, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]


def bm25_retrieve(question: str, n: int = CAND_N) -> list[str]:
    bm25, ids, _ = get_bm25()
    scores = bm25.get_scores(expand_query(question))  # lay→licence alias-expanded query
    top = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)[:n]
    return [ids[i] for i in top]


def rrf(ranked_lists: list[list[str]], k: int = RRF_K) -> list[str]:
    """Reciprocal Rank Fusion: score an id by sum(1/(k+rank)) across lists."""
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, id_ in enumerate(lst, 1):
            scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


def hybrid_retrieve(question: str, k: int = TOP_K, coll=None) -> tuple[list[dict], list[dict]]:
    """Fuse vector + BM25 to top-k chunks. Returns (fused_chunks, vector_hits).
    vector_hits is returned separately so the caller can use the best vector
    distance for the coarse out-of-scope backstop."""
    vhits = vector_retrieve(question, CAND_N, coll)
    fused_ids = rrf([[h["id"] for h in vhits], bm25_retrieve(question, CAND_N)])[:k]
    _, _, chunk_by_id = get_bm25()
    vdist = {h["id"]: h["distance"] for h in vhits}
    fused = []
    for id_ in fused_ids:
        c = chunk_by_id.get(id_)
        if c is None:
            continue
        fused.append({"id": id_, "text": c["text"], "meta": c["metadata"], "distance": vdist.get(id_)})
    return fused, vhits


def expand_hits(hits: list[dict], coll, as_of: date) -> list[dict]:
    """
    Small-to-big retrieval, version-aware. For each hit condition we resolve which held
    version's text applies as of `as_of` (temporal.version_for): unmapped / current-date
    conditions stay on the current version; a mapped text-change condition on a past date
    is SWAPPED to its historic version and served WHOLE (the complete historic condition).
    On the current version, the original rule applies: a small condition
    (≤ EXPAND_FULL_CAP chunks) is pulled whole; a large one pulls only chunk_index ±1 so
    giant conditions can't flood the context. Returns items grouped by condition
    (fused-rank order) and ordered by chunk_index within each.
    """
    _, _, chunk_by_id = get_bm25()
    # chunk_index sets per (version_label, condition) — versions chunk to different sizes.
    ver_cond_idxs: dict[tuple[str, str], set[int]] = {}
    for c in chunk_by_id.values():
        m = c["metadata"]
        ver_cond_idxs.setdefault((m["version_label"], m["condition"]), set()).add(m["chunk_index"])

    # Condition order = order of first appearance in the (already fused-ranked) hits.
    cond_order: list[str] = []
    for h in hits:
        if h["meta"]["condition"] not in cond_order:
            cond_order.append(h["meta"]["condition"])
    top_conds = set(cond_order[:LARGE_TOP_N])  # strongest-matched conditions get full expansion

    # Deterministic chunk ids (must match chunk.py's scheme): f"{version}__cond{cond}_{idx}".
    want: set[str] = set()
    for h in hits:
        c, idx = h["meta"]["condition"], h["meta"]["chunk_index"]
        target = temporal.version_for(c, as_of)  # served version label, or None (before earliest)
        if target is None:
            continue  # historic text not held → serve nothing; the temporal note caveats it
        idxs = ver_cond_idxs.get((target, c), set())
        full = (
            target != versions.CURRENT_LABEL                       # swapped historic → whole held text
            or len(idxs) <= EXPAND_FULL_CAP                        # small current condition → whole
            or (c in top_conds and len(idxs) <= LARGE_MAX_CHUNKS)  # strongly-matched large → whole
        )
        if full:
            for j in idxs:
                want.add(f"{target}__cond{c}_{j}")
        else:
            for j in (idx - 1, idx, idx + 1):  # bounded neighbours for a large, lower-ranked condition
                if j in idxs:
                    want.add(f"{target}__cond{c}_{j}")

    got = coll.get(ids=list(want))  # missing ids are silently skipped
    items = [
        {"text": doc, "meta": meta}
        for doc, meta in zip(got["documents"], got["metadatas"])
    ]

    # Group by condition (best rank first), chunks in reading order within each.
    ordered: list[dict] = []
    for c in cond_order:
        block = sorted(
            (it for it in items if it["meta"]["condition"] == c),
            key=lambda it: it["meta"]["chunk_index"],
        )
        ordered.extend(block)
    return ordered


def build_context(ordered: list[dict]) -> str:
    """Render expanded chunks as labelled, citable extracts — one block per condition."""
    from itertools import groupby

    parts = []
    for i, (_, group) in enumerate(groupby(ordered, key=lambda it: it["meta"]["condition"]), 1):
        block = list(group)
        m = block[0]["meta"]
        vdate = temporal.fmt(versions.BY_LABEL[m["version_label"]]["date"])
        header = (
            f"[Extract {i}] Condition {m['condition']} — {m['condition_title']} "
            f"(consolidation {vdate}, Section {m['section']}, pp.{m['page_start']}-{m['page_end']})"
        )
        body = " ".join(it["text"] for it in block)
        parts.append(f"{header}\n{body}")
    return "\n\n".join(parts)


def answer_question(
    question: str, k: int = TOP_K, coll=None, client=None, model: str = MODEL, as_of: date | None = None
) -> dict:
    """
    Retrieve, ground, and answer. Returns:
        {answer, citations, refused, reason, as_of, retrieved:[{condition,title,pages,distance}]}

    `as_of` is the effective date to answer as of (default = today → current behaviour).
    `coll` / `client` may be injected (e.g. cached by the Streamlit UI) to avoid
    re-opening the store or re-creating the client on every call.
    """
    as_of = as_of or date.today()
    coll = coll or get_collection()
    chunks, vhits = hybrid_retrieve(question, k, coll)
    retrieved_meta = [
        {
            "condition": c["meta"]["condition"],
            "condition_title": c["meta"]["condition_title"],
            "pages": f"{c['meta']['page_start']}-{c['meta']['page_end']}",
            "distance": round(c["distance"], 3) if c["distance"] is not None else None,
            # The version whose text will actually be SERVED for this condition as of the date.
            "version": temporal.version_for(c["meta"]["condition"], as_of),
        }
        for c in chunks
    ]

    # Coarse backstop: obviously out-of-scope → refuse without spending an API call.
    # Judged on the best *vector* distance (a strong BM25 keyword hit should not be
    # blocked by a poor vector score — that's the whole point of hybrid).
    best = min((h["distance"] for h in vhits), default=float("inf"))
    if not chunks or best > DISTANCE_FLOOR:
        return {
            "refused": True,
            "answer": "",
            "citations": [],
            "reason": (
                "No sufficiently relevant section was found in the electricity supply "
                "licence conditions for this question."
            ),
            "as_of": as_of.isoformat(),
            "retrieved": retrieved_meta,
        }

    # In scope → Phase 7 pipeline: plan sub-queries → union retrieve → grouped-by-obligation
    # synthesis. A specific question yields 1 sub-query → behaves like the old single-query path;
    # a broad one is decomposed so ALL relevant obligations are surfaced. (Lazy import avoids a
    # planner<->rag circular import.)
    try:
        from src import planner
    except ImportError:
        import planner
    result = planner.answer_broad(question, coll=coll, as_of=as_of, client=client, model=model)
    union = result.pop("_union", [])
    # Transparency + eval meta reflects the FULL union fed to synthesis (every sub-query), not just
    # the backstop's single-query top-k, so retrieval-hit / version checks see everything served.
    result["retrieved"] = [
        {
            "condition": c["meta"]["condition"],
            "condition_title": c["meta"]["condition_title"],
            "pages": f"{c['meta']['page_start']}-{c['meta']['page_end']}",
            "distance": round(c["distance"], 3) if c["distance"] is not None else None,
            "version": temporal.version_for(c["meta"]["condition"], as_of),
        }
        for c in union
    ] or retrieved_meta
    result["as_of"] = as_of.isoformat()
    # Show every mapped cited condition's history on a BROAD answer (completeness); keep the
    # anti-clutter cap of 2 for narrow answers. (Only 5 conditions are mapped, so 8 = "all".)
    is_broad = bool(result.get("plan", {}).get("is_broad"))
    result["history"] = history.views_for(
        result.get("citations", []), as_of, limit=8 if is_broad else 2
    )
    return result


def _format_cli(q: str, r: dict) -> str:
    lines = [f"Q: {q}", f"(as of {r.get('as_of', 'today')})", ""]
    if r["refused"]:
        lines.append("REFUSED — not in source material")
        lines.append(f"  reason: {r['reason']}")
    else:
        lines.append(f"A: {r['answer']}")
        lines.append("")
        lines.append("Citations:")
        for c in r["citations"]:
            lines.append(f"  - Condition {c['condition']} — {c['condition_title']} (pp.{c['pages']})")
    lines.append("")
    lines.append("Retrieved (fused rank):")
    for m in r["retrieved"]:
        d = m["distance"] if m["distance"] is not None else "kw"
        v = m.get("version") or "?"
        lines.append(
            f"  [{d}] Cond {m['condition']} — {m['condition_title']} (v{v}, pp.{m['pages']})"
        )
    for h in r.get("history", []):
        lines.append("")
        if h["kind"] == "text-change":
            side = "after" if h["on_after"] else "before"
            lines.append(f"Version history — Cond {h['condition']} ({h['title']}): "
                         f"text changed {h['change_date']} (as of {h['as_of']}: {side} the change)")
            parts = []
            for s in h["diff"]:
                if s["type"] == "add":
                    parts.append(f"[+ {s['text']}]")
                elif s["type"] == "del":
                    parts.append(f"[- {s['text']}]")
                elif s["type"] == "gap":
                    parts.append("…")
                else:
                    parts.append(s["text"])
            lines.append(f"  what changed: {' '.join(parts)}{'  …(+more)' if h['diff_truncated'] else ''}")
        else:
            state = "existed" if h["existed"] else "did NOT exist yet"
            lines.append(f"Version history — Cond {h['condition']} ({h['title']}): "
                         f"introduced {h['introduced']} (as of {h['as_of']}: {state})")
    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print('Usage: venv/bin/python src/rag.py "your question" [YYYY-MM-DD]')
        sys.exit(1)
    as_of = None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[-1]):
        as_of = date.fromisoformat(args.pop())
    q = " ".join(args)
    print(_format_cli(q, answer_question(q, as_of=as_of)))
