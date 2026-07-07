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
- [x] Download Ofgem Standard Licence Conditions (electricity and/or gas supply) from Ofgem's public site — electricity supply SLC, consolidated to 1 Aug 2025
- [x] Save raw source files to `data/raw/` — `electricity-supply-slc-consolidated-2025-08.pdf` (611 pages, 3.7 MB)
- [x] Record provenance (source URL, retrieval date) — confirms public-only — see `docs/provenance.md`
- **Verify:** ✅ file present, ✅ readable (611 pages, real text via pdfplumber), ✅ provenance noted (electricity only for v0)

## Phase 2 — Ingestion pipeline (v0)
- [x] Load document(s): PDF/HTML → text — `src/extract_pages.py`, pypdf → `data/interim/slc_pages.jsonl` (611 pages cached; pdfplumber too slow)
- [x] Chunk text, attaching metadata (source, section/condition ref, page) — `src/chunk.py`, structure-aware by Condition (Option B), 111 conditions → 1133 chunks, ~175-word windows
- [x] Embed + store chunks in ChromaDB — `src/embed.py`, default embedder, collection `ofgem_slc_electricity` (1133), idempotent reset
- [x] Persist the Chroma store to disk — `chroma/` (gitignored)
- **Verify:** ✅ 1133 chunks (sensible); ✅ 3 chunks spot-checked (text+metadata correct); ✅ 0 boilerplate leaks; ✅ end-to-end smoke query works; ✅ parser completeness bug (missed 19AA/21BA/28AA/28AD) caught + fixed

## Phase 3 — Retrieval + grounded generation (v0)
- [x] Query → retrieve top-k relevant chunks — `src/rag.py`, k=6 from Chroma
- [x] Build a grounded prompt: answer ONLY from retrieved context, cite source + section, refuse if no adequate match — LLM-judged refusal + lenient distance backstop
- [x] Call Claude, return answer + citations — Opus 4.8, adaptive thinking, structured JSON output (`answer_question()` entry point)
- **Verify:** ✅ 5 taxonomy questions answered, grounded + cited to correct conditions; ✅ out-of-scope (gas boiler) refused, not invented; ✅ 21BA "Backbilling" now retrieved at rank 1

## Phase 4 — Streamlit UI
- [x] Question input, answer display, citation list, clear "not in source material" state — `app/main.py`, single-turn form, example questions, provenance/disclaimer caption
- [x] Wire UI to the retrieval+generation function — `answer_question()`, cached collection + client (`@st.cache_resource`)
- [x] Run locally (`streamlit run`) — headless on :8501, retrieved-sources expander for transparency
- **Verify:** ✅ end-to-end in browser (title "RIA"); ✅ answer + citations visible; ✅ out-of-scope refusal visible
- **Refinement:** neighbour expansion (chunk_index ±1) added to `src/rag.py` so multi-part conditions (e.g. 21BA exceptions) reach Claude complete

## Phase 5 — Lightweight evals
- [x] Encode taxonomy questions as test cases with expected source areas + expected refusals — `evals/cases.yaml` (10 cases; expected answer/refuse + expected conditions)
- [x] Script to run the set and record pass/fail per case — `evals/run_evals.py` (deterministic: decision accuracy + retrieval/citation hit; writes `results_*.json`)
- [x] Short eval report — `evals/report.md` (baseline 9/10, O4 fix tried+reverted, hybrid-retrieval recommendation, Opus vs Haiku A/B)
- **Verify:** ✅ runner runs clean; ✅ report reflects real behaviour (0 hallucinations, 3/3 correct refusals, O4 the sole false refusal)
- **Findings:** O4 vocabulary-gap false refusal → hybrid keyword+vector retrieval is the evidenced fix (deferred); Opus 4.8 justified by A/B (equal substance, cleaner citations)

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

## Review — v0 close-out (Phases 0–5 complete, 2026-07-07)

**Outcome:** a demoable, eval-backed RAG assistant grounded in the Ofgem electricity
supply SLCs — ingest → retrieve → grounded answer with condition-level citations →
refuse when unsupported → Streamlit UI. Baseline eval: 9/10, 0 hallucinations, 3/3
correct refusals. On GitHub, secret-safe throughout.

### Decisions made
- **Stack:** Python 3.14.4 (everything installed — no fallback to 3.12 needed);
  ChromaDB built-in embedder (`all-MiniLM-L6-v2`, 256-token cap, no PyTorch);
  Opus 4.8 for generation (adaptive thinking, structured JSON output); Streamlit.
- **Corpus:** electricity supply SLCs only, consolidated 1 Aug 2025; dated PDF chosen
  over the EPR "current" URL for reproducibility.
- **Ingestion:** `pypdf` (not `pdfplumber`) for speed; page cache → chunk → embed as
  separate re-runnable stages; **structure-aware chunking by Condition** (Option B);
  ~175-word windows w/ 25-word overlap; **condition-level citations**.
- **Retrieval/generation:** k=6; **LLM-judged refusal** (primary) + lenient distance
  backstop; **neighbour expansion (±1)** so multi-part conditions arrive complete.
- **Evals:** deterministic grading (decision accuracy + retrieval/citation hit);
  taxonomy-driven cases; model A/B (Opus vs Haiku).

### What changed from the plan
- `pdfplumber` → `pypdf` (pdfplumber too slow; timed out / froze the terminal).
- Added **neighbour expansion** (not originally planned) after multi-part conditions
  (21BA exceptions) came back truncated.
- **O4 fix journey:** parser bug found in Phase 2 (multi-letter conditions 19AA/21BA/
  28AA/28AD silently merged) → fixed; later O4 "embed titles" fix tried, **measured,
  reverted** (insufficient) → hybrid retrieval identified as the real fix, **deferred**.
- Added `docs/query-taxonomy.md` as the eval seed; added the Opus-vs-Haiku A/B.

### Lessons (full log: `tasks/lessons.md`)
- Structure-aware chunking needs a completeness check; the end-to-end smoke query, not
  unit stats, exposed the silent condition merge.
- Distance thresholds are a poor refusal mechanism with a weak embedder → LLM-judged.
- Measure fixes, don't assume — the "obvious" O4 fix didn't work.
- Model capability differs by feature (Haiku rejects adaptive thinking/effort).

### Known limitations / open items
- **O4 vocabulary-gap false refusal** — the one measured weakness; **hybrid keyword+vector
  retrieval** is the evidenced fix and the highest-value next change.
- Citation-format grader is strict (conflates "found" with "formatted"); tighten the
  schema field description + a normalising matcher.
- Corpus is electricity **supply** only — complaints-handling / Guaranteed-Standards
  questions (D1/D2) are correctly out of scope; answering them = corpus expansion.
- **Phase 6 (temporal/version awareness)** remains the intended differentiator, to build
  on these fundamentals.
