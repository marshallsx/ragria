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

## Phase 6 — Temporal / version awareness (electricity supply SLCs)
**Status:** PLANNING — sign-off required before any code. The differentiator: answer
"as of date X" from the version in force at X, cite version + effective dates, and
NEVER present superseded text as current.

### Correctness rule (non-negotiable)
- Validity is PER CONDITION, and a mapped condition's timeline is CONTIGUOUS — no internal
  gaps. A condition is in force for its whole life; the only question is which TEXT applied
  on date X. We only map conditions whose change history we can make gap-free.
- REFUSAL applies only to genuinely-unknown territory: dates before our earliest knowledge,
  the future, or conditions we have NOT mapped — never a hole inside a mapped condition's life.
- The cleanest gap-free case is an INTRODUCED condition (an "existence boundary"): it did
  not exist before its introduction date, and exists after — inherently single-event, and
  correct for the entire pre-introduction period with no intermediate versions to hold.
- Why per-condition, not per-version: a whole-version "nothing changed yet" window is tiny
  (Ofgem modified the supply licence constantly), so almost every date would refuse.

### Scope — AGREED: per-condition, scoped to two clean INTRODUCED conditions
- HELD VERSIONS (3 real consolidations; all-conditions TEXT ingested so RITA has the body):
  v2019 (3 Aug 2019), v2022 (14 Apr 2022), v2025 (1 Aug 2025, current).
- DEMO CONDITIONS (dated guarantee) — both introduced after 2022, verified absent in v2019
  & v2022, present in v2025 (existence-boundary demo):
  - **25E — Power to direct Energy Bill Support Scheme Payments** — introduced 24 Sep 2022.
  - **4D — Protecting Domestic Customer Credit Balances** — introduced 20 Sep 2023.
- SLC 47 DEFERRED: verified too volatile (multiple MHHS rewrites 2019→2025; would need many
  intermediate versions for a gap-free timeline). Revisit later as "scale-by-data" work.
- Conditions NOT mapped: undated/current answers only; a dated query REFUSES.
- Electricity **supply** SLCs only. No gas.
- DEFAULT BEHAVIOUR: a question with NO date is always answered **as of today** (= the
  current version, v2025) — exactly as RITA behaves now. The "as of date" picker defaults
  to today; supplying an EARLIER date is the only thing that triggers historic resolution.
  So existing (undated) usage and evals are unchanged.

### Data — sources (downloaded to data/raw/, gitignored)
- Consolidations (readable body text): v2019 (3 Aug 2019, 484pp), v2022 (14 Apr 2022,
  550pp), v2025 (1 Aug 2025, 611pp). Consolidated PDFs labelled "not to be relied on".
- 25E introduction: effective **24 Sep 2022** (EBSS supplier licence decision notice).
- 4D introduction: effective **20 Sep 2023** (Decision OFG1163 published 26 Jul 2023, "56
  days after" → 20 Sep 2023; confirmed by the 20 Sep 2023 erratum notice).
- Authoritative effective dates: Ofgem modification notices / EPR (epr.ofgem.gov.uk).
- Note: 4D had minor errata (Sep 2023, Jul 2024) — corrections; existence-boundary demo is
  correct regardless. Holding errata versions is later refinement.

### Metadata per chunk (add to existing schema)
- `version_label` (e.g. `2019-08-03` / `2022-04-14` / `2025-08-01`) + `version_date`.
- `source_authority` — consolidated (reference) vs EPR (definitive); upgradable field.
- `url`.
- Per-mapped-condition timeline held alongside (e.g. 25E: did not exist before 2022-09-24,
  in force from 2022-09-24) — maps "as of date X" → "did not exist" / the held in-force
  text; unmapped conditions REFUSE on a dated query.

### Retrieval — "as of date X" (per condition)
- For a verified condition, resolve the held version carrying its in-force text at X; if
  none is held for X → REFUSE.
- Restrict retrieval (vector + BM25 + neighbour expansion) to that version's chunks, then
  answer + cite the version + the condition's effective range.
- Non-verified condition + a date supplied → REFUSE (no dated guarantee yet).
- Undated / default = current version (v2025).

### UI
- "As of date" picker (default = today).
- Banner showing which version answered + its effective range; explicit uncertainty state
  when the date isn't covered.

### Date interpretation — imprecise / ambiguous dates (never guess a side)
- Precise date (picker) → resolve directly (the picker exists precisely to be unambiguous).
- A period mentioned in the question (e.g. "in 2022") is resolved against the queried
  condition's change points:
  - wholly on ONE side of every change → answer for that single state (e.g. "in 2021" for
    25E → did not exist all year);
  - STRADDLES a change/introduction boundary → do NOT pick a side. Surface the boundary and
    give BOTH states (e.g. "25E was introduced 24 Sep 2022: before → didn't exist; from →
    requires …"), and invite a precise date.
- Extract the date/period from the question (LLM); if none, use the picker (default today).

### Verify gate (4D + 25E — existence boundary)
- [ ] "25E / 4D as of a date BEFORE its introduction" → "did not exist in the licence as of
      that date; introduced [date]" (correct for the whole pre-introduction period).
- [ ] "25E / 4D as of today" → the current text + introduction/effective date cited.
- [ ] A current-date query answers from v2025 (current), never a superseded version.
- [ ] A dated query on an UNMAPPED condition → RITA refuses / says it can't date that yet.

### Build steps (existence-boundary increment — tick as we go)
- [x] Pin 4D's exact introduction date — **20 Sep 2023** (Decision OFG1163 pub 26 Jul 2023
      + "56 days"; confirmed by the 20 Sep 2023 erratum).
- [x] Temporal module (`src/temporal.py`): mapped-condition timelines (25E 2022-09-24; 4D
      2023-09-20) + `existed()` / `temporal_notes()`.
- [x] `answer_question` gains an `as_of` date (default today); injects temporal facts +
      system-prompt rules (never present current text as applying before a condition existed;
      pre-existence → "did not exist / introduced [date]"; straddling period → both states;
      unmapped conditions not asserted for past dates). CLI-verified for 25E & 4D.
- [x] UI "⏳ As of date" picker (default today, max today) + historic-date banner.
- [ ] Verify gate (25E + 4D existence boundary) + temporal eval cases.
- [ ] Flip public copy to present tense once real.
- Deferred: ingest v2019/v2022 historic TEXT — only needed for text-CHANGE conditions (e.g.
  SLC 47 later); the existence-boundary demo doesn't need it (25E/4D didn't exist then).

### Resolved decisions
- Validity: PER CONDITION, contiguous (no internal gaps); refusal only outside covered
  period / unmapped conditions. ✅
- Demo conditions: 25E (introduced 24 Sep 2022) + 4D (introduced 20 Sep 2023), existence
  boundary. SLC 47 deferred (too volatile). ✅
- Held versions available in data/raw: v2019, v2022, v2025 (historic-text ingestion deferred). ✅
- Default: no date ⇒ answered as of TODAY (current version, v2025) — unchanged behaviour. ✅

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

### Post-v0 improvement — hybrid retrieval (O4 fixed)
- **Implemented hybrid retrieval** (BM25 + vector, RRF fusion; title field-boost ×8;
  whole-condition expansion for small conditions). O4 false refusal resolved.
  **Eval: 9/10 → 10/10, retrieval 6/7 → 7/7, zero regressions, zero hallucinations.**

### Known limitations / open items
- Citation-format grader is strict (conflates "found" with "formatted"); tighten the
  schema field description + a normalising matcher.
- Eval set is small (10 cases) — expand the taxonomy for a stronger signal.
- Corpus is electricity **supply** only — complaints-handling / Guaranteed-Standards
  questions (D1/D2) are correctly out of scope; answering them = corpus expansion.
- **Phase 6 (temporal/version awareness)** remains the intended differentiator, to build
  on these fundamentals.
