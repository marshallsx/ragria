# Regulatory Intelligence Assistant — PoC Build Plan

**Status:** APPROVED — Phase 0 in progress
**Goal:** Learning-first PoC. Build the RAG pipeline end-to-end, understand every part, produce a demoable, eval-backed artefact.
**Builds on:** existing PRD (Regulatory Intelligence Assistant — Energy & Utilities).

---

## Stack (confirmed)

- **Language/env:** Python in WSL2, virtual environment
- **Vector store + embeddings:** ChromaDB (built-in default embeddings — no PyTorch, no separate model)
- **Generation:** Anthropic API (Claude)
- **UI:** Streamlit (from the start)
- **Ingestion:** pdfplumber / pypdf for Ofgem documents
- **Config/secrets:** python-dotenv (API key never committed to git)

## Scope

**In (v0):** one corpus (Ofgem Standard Licence Conditions), ingest → chunk → embed → retrieve → grounded answer with citations → refuse when no good match; Streamlit UI; lightweight evals from the query taxonomy.

**Out (v0), noted for later:** version / effective-date (temporal) awareness — this is the eventual differentiator and becomes Phase 2 *after* v0 works; broader corpus (codes, decisions); cloud deployment; any non-public data.

---

## Phase 0 — Environment & project setup
*Walk-through, one numbered command at a time. Beginner-paced.*

- [x] Confirm WSL2 working and Python version (`python3 --version`) — Python 3.14.4 confirmed
- [x] Create project folder on the **local Linux filesystem** (NOT OneDrive) — `~/projects/ragria`
- [x] Create and activate a virtual environment (`venv`) — Python 3.14.4, at `venv/`
- [x] Create project structure: `data/` `src/` `app/` `evals/` `tasks/` (+ `data/raw/`, `docs/`)
- [x] Create `requirements.txt` and install dependencies — all installed & import cleanly on Python 3.14.4 (no drop to 3.12 needed)
- [x] Create `.gitignore` (excludes `.env`, `venv/`, `data/`, Chroma store)
- [x] Create `.env` and add Anthropic API key — loads via python-dotenv, verified masked
- [x] `git init` + first commit + create GitHub repo — private repo at github.com/marshallsx/ragria, pushed to `main`
- **Verify:** ✅ venv active (Py 3.14.4), ✅ packages import, ✅ `.env` loads (masked), ✅ key NOT in git status / NOT on GitHub

## Phase 1 — Get the corpus
- [ ] Download Ofgem Standard Licence Conditions (electricity and/or gas supply) from Ofgem's public site
- [ ] Save raw source files to `data/raw/`
- [ ] Record provenance (source URL, retrieval date) — confirms public-only
- **Verify:** files present, readable, provenance noted

## Phase 2 — Ingestion pipeline (v0)
- [ ] Load document(s): PDF/HTML → text
- [ ] Chunk text, attaching metadata (source, section/condition ref, page)
- [ ] Embed + store chunks in ChromaDB
- [ ] Persist the Chroma store to disk
- **Verify:** chunk count sensible; spot-check 3 chunks have correct text + metadata

## Phase 3 — Retrieval + grounded generation (v0)
- [ ] Query → retrieve top-k relevant chunks
- [ ] Build a grounded prompt: answer ONLY from retrieved context, cite source + section, refuse if no adequate match
- [ ] Call Claude, return answer + citations
- **Verify:** run 5 taxonomy questions; answers grounded + cited; an out-of-scope question triggers refusal, not invention

## Phase 4 — Streamlit UI
- [ ] Question input, answer display, citation list, clear "not in source material" state
- [ ] Wire UI to the retrieval+generation function
- [ ] Run locally (`streamlit run`)
- **Verify:** end-to-end in the browser; citations visible; refusal visible

## Phase 5 — Lightweight evals
- [ ] Encode taxonomy questions as test cases with expected source areas + expected refusals
- [ ] Script to run the set and record pass/fail per case
- [ ] Short eval report (what passed, what didn't, where retrieval is weak)
- **Verify:** eval script runs clean; report reflects real behaviour

## Phase 6 — (Later) Temporal / version awareness
- [ ] Capture version + effective date per chunk
- [ ] Support "as of date X" queries; never cite a superseded version
- *Out of scope for v0 — the moat, built once fundamentals are solid.*

---

## Guardrails for this build
- Sign-off required on this plan before Phase 0 begins.
- API key never committed (checked at Phase 0 verify).
- Public Ofgem data only — no Centrica/British Gas internal material.
- Each phase has a verify gate; no item ticked until proven.
- Destructive/irreversible actions flagged before running (none expected beyond standard git).

## Review (to complete as we go)
- _Decisions made:_
- _What changed from plan:_
- _Lessons (→ tasks/lessons.md):_
