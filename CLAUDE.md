# Regulatory Intelligence Assistant — Project Memory

> Personal working preferences live in `~/.claude/CLAUDE.md` and apply automatically.
> This file holds project-specific context only.

## What this is

A learning-first RAG proof-of-concept: a Q&A assistant grounded in **publicly available Ofgem Standard Licence Conditions**. User asks a regulatory question; the assistant retrieves the relevant sections, answers **only** from that grounded context, cites source + section, and **refuses when it has no adequate match**. Goal is twofold: learn the full RAG pipeline end-to-end, and produce a demoable, eval-backed artefact.

## Stack

- Python in WSL2, virtual environment (`venv`)
- **ChromaDB** — vector store + built-in default embeddings (no PyTorch, no separate embedding model)
- **Anthropic API** (Claude) — grounded answer generation
- **Streamlit** — UI (from the start)
- **pdfplumber / pypdf** — ingest Ofgem documents
- **python-dotenv** — config; API key never committed

## Project layout

- `tasks/` — build plan and lessons
- `src/` — ingestion, retrieval, generation
- `app/` — Streamlit UI
- `evals/` — eval cases (from the query taxonomy) + report
- `data/raw/` — source documents (gitignored)
- `docs/` — PRD, query taxonomy (reference)

## Common commands

- Activate venv: `source venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Run the app: `streamlit run app/main.py` (Phase 4)
- Ingestion pipeline (run once, in order):
  - `venv/bin/python src/extract_pages.py` — PDF → page cache (`data/interim/slc_pages.jsonl`)
  - `venv/bin/python src/chunk.py` — cache → chunks (`data/interim/slc_chunks.jsonl`)
  - `venv/bin/python src/embed.py` — chunks → ChromaDB (`chroma/`, ~6 min first run)
- Ask a question (grounded answer + citations): `venv/bin/python src/rag.py "your question"`

## Scope

**In (v0):** Ofgem Standard Licence Conditions only; ingest → chunk → embed → retrieve → grounded answer with citations → refuse on no match; Streamlit UI; lightweight evals from the query taxonomy.

**Out (v0), noted for later:** version / effective-date (temporal) awareness — this is the eventual differentiator and is **Phase 6, built only after v0 works**; broader corpus (industry codes, decisions); cloud deployment; any non-public data.

## Project rules (in addition to global preferences)

- **Public Ofgem data only.** No Centrica / British Gas internal, confidential, or proprietary material — ever.
- **Follow the plan in `tasks/todo.md`.** Work phase by phase; do not skip ahead.
- **Verify gate on every phase** — nothing marked done until proven to work (spot-check, run, diff).
- **Sign-off before implementing** each phase; check in, don't just start.
- **Numbered CLI steps, one command at a time** — Scott is a terminal beginner; wait for each to succeed before the next.
- Do not build temporal / version awareness yet. Fundamentals first.

## Current plan

@tasks/todo.md
