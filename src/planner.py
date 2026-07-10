"""
Phase 7 — Corpus-aware query planner (broad-query completeness).

Turns a question into 1..N focused SEARCH sub-queries so a BROAD question ("what obligations do
we have to vulnerable customers?") retrieves ALL the relevant conditions, not just the best match,
while a SPECIFIC question stays a single query (no behaviour change vs today).

Corpus-aware: first a wide-net retrieve gets the candidate conditions that actually EXIST in the
corpus; their titles are shown to the planner so its sub-queries use the licence's own vocabulary
and cover the surfaced obligation areas. The original question is ALWAYS kept as a sub-query, so
planning can only ADD coverage — never regress below today's single-query behaviour.

Baseline (Step 0) showed a targeted sub-query reaches conditions a broad query structurally can't
(e.g. "back-billing" finds Cond 21BA where "billing obligations" misses it even at depth 40) —
that is exactly what this planner exploits.

CLI smoke test:  venv/bin/python src/planner.py "what obligations do we have to vulnerable customers?"
"""
from __future__ import annotations

import json
import sys

try:  # works both as `src.planner` (app/evals) and `python src/planner.py`
    from src import rag
except ImportError:
    import rag

WIDE_NET = 40          # depth of the wide-net retrieve that builds the candidate landscape
MAX_CANDIDATES = 25    # cap candidate conditions shown to the planner (keeps the prompt small)
MAX_SUBQUERIES = 6     # total sub-queries incl. the original (bounds cost/latency + precision drift)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "is_broad": {"type": "boolean"},
        "subqueries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "focus": {"type": "string"},   # short obligation-area label
                    "query": {"type": "string"},   # focused, keyword-rich search phrase
                },
                "required": ["focus", "query"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["is_broad", "subqueries"],
    "additionalProperties": False,
}

PLAN_SYSTEM = (
    "You are a retrieval planner for a RAG assistant grounded ONLY in Ofgem electricity supply "
    "Standard Licence Conditions. Given a user question and the candidate licence conditions that "
    "exist in the corpus, produce focused SEARCH sub-queries that together retrieve EVERY relevant "
    "obligation.\n"
    "Rules:\n"
    "- If the question is SPECIFIC (about one thing), set is_broad=false and return exactly ONE "
    "sub-query that restates it. Do NOT broaden a specific question.\n"
    "- If the question is BROAD (asks for obligations / duties / responsibilities across an area), "
    "set is_broad=true and decompose into one focused sub-query PER distinct obligation area. Use "
    "the candidate condition TITLES to phrase sub-queries in the licence's own vocabulary.\n"
    "- You MAY add a sub-query for a specific obligation you are confident the licence covers even "
    "if it is not in the candidate list (e.g. a named mechanism), but do NOT invent obligations.\n"
    f"- Return at most {MAX_SUBQUERIES - 1} sub-queries (the original question is added separately). "
    "Prefer precision: only areas genuinely responsive to the question.\n"
    "- Each 'query' is a short keyword-rich search phrase, not a sentence."
)


def _candidate_conditions(question: str, coll) -> list[tuple[str, str]]:
    """Wide-net retrieve → ordered unique (condition, title) pairs that exist in the corpus."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(cond: str, title: str) -> None:
        if cond not in seen:
            seen.add(cond)
            pairs.append((cond, title))

    for h in rag.vector_retrieve(question, WIDE_NET, coll):
        add(h["meta"]["condition"], h["meta"]["condition_title"])
    bm25, ids, cbi = rag.get_bm25()
    scores = bm25.get_scores(rag.expand_query(question))
    top = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)[:WIDE_NET]
    for i in top:
        m = cbi[ids[i]]["metadata"]
        add(m["condition"], m["condition_title"])
    return pairs[:MAX_CANDIDATES]


def plan(question: str, coll=None, client=None, model: str | None = None) -> dict:
    """Return {'is_broad': bool, 'subqueries': [str, ...]} — sub-queries ALWAYS include the
    original question first. Specific question → [question]; broad → several focused phrases."""
    coll = coll or rag.get_collection()
    model = model or rag.MODEL
    client = client or rag.get_client()

    candidates = _candidate_conditions(question, coll)
    cand_str = "\n".join(f"- Condition {c}: {t}" for c, t in candidates)
    user = f"Question: {question}\n\nCandidate conditions in the corpus:\n{cand_str}"

    fmt = {"type": "json_schema", "schema": PLAN_SCHEMA}
    kwargs = dict(model=model, max_tokens=1024, system=PLAN_SYSTEM,
                  messages=[{"role": "user", "content": user}])
    if "haiku" in model:
        kwargs["output_config"] = {"format": fmt}
    else:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": "low", "format": fmt}
    resp = client.messages.create(**kwargs)
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    # Original question ALWAYS first (safety net — planning can only add coverage), then the
    # planner's focused sub-queries; dedup case-insensitively, cap total at MAX_SUBQUERIES.
    subs, seen = [], set()
    for q in [question] + [(sq.get("query") or "").strip() for sq in data.get("subqueries", [])]:
        key = q.lower()
        if q and key not in seen:
            seen.add(key)
            subs.append(q)
        if len(subs) >= MAX_SUBQUERIES:
            break
    return {"is_broad": bool(data.get("is_broad")), "subqueries": subs}


K_PER = 6       # chunks pulled per sub-query (reuses the existing hybrid retriever)
BUDGET = 40     # max unique chunks in the union fed to synthesis (context/cost cap)


def plan_and_retrieve(question: str, coll=None, client=None, model: str | None = None,
                      k_per: int = K_PER, budget: int = BUDGET) -> tuple[dict, list[dict]]:
    """Plan sub-queries, retrieve each via the existing hybrid retriever, then UNION + dedup by
    chunk id with ROUND-ROBIN interleave across sub-queries: each obligation area contributes its
    rank-1 chunk before any contributes its rank-2, so the budget cap can't starve a whole area.
    Returns (plan, union_chunks). A specific question → one sub-query → behaves like today."""
    coll = coll or rag.get_collection()
    p = plan(question, coll=coll, client=client, model=model)
    lists = [rag.hybrid_retrieve(sq, k_per, coll)[0] for sq in p["subqueries"]]
    union: list[dict] = []
    seen: set[str] = set()
    maxlen = max((len(lst) for lst in lists), default=0)
    for depth in range(maxlen):
        for lst in lists:
            if depth < len(lst):
                c = lst[depth]
                if c["id"] not in seen:
                    seen.add(c["id"])
                    union.append(c)
                    if len(union) >= budget:
                        return p, union
    return p, union


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "what obligations do we have to vulnerable customers?"
    p = plan(q)
    print(f"question : {q}")
    print(f"is_broad : {p['is_broad']}")
    print(f"sub-queries ({len(p['subqueries'])}):")
    for i, s in enumerate(p["subqueries"]):
        print(f"  {i}. {s}")
