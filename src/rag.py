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

import sys
from pathlib import Path

import anthropic
import chromadb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "chroma"
COLLECTION = "ofgem_slc_electricity"

MODEL = "claude-opus-4-8"
TOP_K = 6
# Coarse backstop only. The LLM makes the real refusal call; this just avoids an
# API round-trip when even the closest chunk is clearly unrelated.
# Verify-gate calibration: in-scope questions ran best-distance 0.71-0.95; an
# out-of-scope question was 1.07 — too close to separate cleanly, so the backstop
# stays lenient and the LLM handles the nuanced refusals. Revisit in Phase 5 evals.
DISTANCE_FLOOR = 1.6

load_dotenv(ROOT / ".env")

SYSTEM = """You are a regulatory research assistant for the Ofgem Electricity Supply \
Standard Licence Conditions (consolidated to 1 August 2025).

You are given a user question and a set of numbered extracts retrieved from that \
document. Each extract is labelled with its Condition number, title, and page range.

Answer using only the information in the provided extracts:
- Do not use outside knowledge or general assumptions about energy regulation.
- If the extracts do not contain enough information to answer, do not guess. Set \
refused to true, leave answer empty, and in reason briefly say what was missing.
- When you answer, ground every statement in the extracts and cite the specific \
conditions you relied on. Do not add requirements that are not in the text.
- Keep the answer concise and factual.

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
                    "condition": {"type": "string"},
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


def retrieve(question: str, k: int = TOP_K) -> list[dict]:
    """Return the top-k chunks with metadata + distance, nearest first."""
    coll = get_collection()
    res = coll.query(query_texts=[question], n_results=k)
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append({"text": doc, "meta": meta, "distance": dist})
    return out


def build_context(chunks: list[dict]) -> str:
    """Render retrieved chunks as labelled, citable extracts."""
    parts = []
    for i, c in enumerate(chunks, 1):
        m = c["meta"]
        header = (
            f"[Extract {i}] Condition {m['condition']} — {m['condition_title']} "
            f"(Section {m['section']}, pp.{m['page_start']}-{m['page_end']})"
        )
        parts.append(f"{header}\n{c['text']}")
    return "\n\n".join(parts)


def answer_question(question: str, k: int = TOP_K) -> dict:
    """
    Retrieve, ground, and answer. Returns:
        {answer, citations, refused, reason, retrieved:[{condition,title,pages,distance}]}
    """
    chunks = retrieve(question, k)
    retrieved_meta = [
        {
            "condition": c["meta"]["condition"],
            "condition_title": c["meta"]["condition_title"],
            "pages": f"{c['meta']['page_start']}-{c['meta']['page_end']}",
            "distance": round(c["distance"], 3),
        }
        for c in chunks
    ]

    # Coarse backstop: obviously out-of-scope → refuse without spending an API call.
    best = chunks[0]["distance"] if chunks else float("inf")
    if not chunks or best > DISTANCE_FLOOR:
        return {
            "refused": True,
            "answer": "",
            "citations": [],
            "reason": (
                "No sufficiently relevant section was found in the electricity supply "
                "licence conditions for this question."
            ),
            "retrieved": retrieved_meta,
        }

    context = build_context(chunks)
    user_content = f"Question: {question}\n\nRetrieved extracts:\n\n{context}"

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from .env
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )

    if resp.stop_reason == "refusal":
        return {
            "refused": True,
            "answer": "",
            "citations": [],
            "reason": "The request was declined by a safety filter.",
            "retrieved": retrieved_meta,
        }

    # With thinking enabled, the first block is a thinking block — take the text block.
    import json

    text = next(b.text for b in resp.content if b.type == "text")
    result = json.loads(text)
    result["retrieved"] = retrieved_meta
    return result


def _format_cli(q: str, r: dict) -> str:
    lines = [f"Q: {q}", ""]
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
    lines.append("Retrieved (nearest first):")
    for m in r["retrieved"]:
        lines.append(
            f"  [{m['distance']}] Cond {m['condition']} — {m['condition_title']} (pp.{m['pages']})"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: venv/bin/python src/rag.py "your question"')
        sys.exit(1)
    q = " ".join(sys.argv[1:])
    print(_format_cli(q, answer_question(q)))
