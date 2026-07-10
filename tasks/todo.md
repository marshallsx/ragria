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
**Status:** INCREMENT 2 BUILT & VERIFIED. RITA answers "as of a past date" with the version of a
condition's TEXT in force then, across **three** mapped text-change conditions plus the two
existence-boundary conditions (25E + 4D, increment 1):
- **Cond 28 (Prepayment Meters)** — pre-reform v2022 before 8 Nov 2023 / post-reform v2025 after.
- **Cond 0A (Treating Non-Domestic Customers Fairly)** — microbusiness-scope v2022 before 1 Jul
  2024 / all-non-domestic v2025 after.
- **Cond 21B (Billing based on meter readings)** — **v2019** before 31 Dec 2020 / v2025 after
  (paragraph 21B.5A, smart-meter monthly billing; first mapping to serve v2019).
Each states the consolidation/effective date it relied on, and still flags non-existence /
unmapped conditions. Corpus holds **three** version-tagged consolidations (**v2019 + v2022 +
v2025**); "current" is derived as the latest held version (no hardcoded date anywhere). A
**change-detector** (`src/detect_changes.py` → `docs/change-map.md`) classifies every condition
across held snapshots so mapped conditions are chosen from DATA (0A and 21B both came from it,
mod-history confirmed; 28A was investigated and rejected — spent condition, immaterial change).
Eval **19/19** on the core temporal set. A **hardened suite** (31 cases: +paraphrases, +refusals,
+temporal edges) with retrieval rank/recall@k, an independent **faithfulness LLM-judge**, and a
history-view check measures quality: **31/31 decisions, retrieval + citation 26/26, recall@1 20/26,
faithfulness 26/26 (0 hallucinations), 0 false answers**. It surfaced two real weaknesses which were
then FIXED: **P1** (false refusal — large-condition expansion: top-2 matched conditions now served
whole) and **P3** (retrieval miss of Cond 26 — lay→licence query synonym expansion, e.g. "cutting
off"→disconnection, "extra help/vulnerable"→priority services register). See `evals/report.md`.
Next: map more conditions (billing 31H, SoLR 8, more introduced), or add an "expired/ceased
condition" category (e.g. 28A, spent 30 Jun 2021); multi-change (e.g. SLC 47, confirmed volatile)
once enough intermediate versions are held.

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

### Verify gate (4D + 25E — existence boundary) ✅ PASSED
- [x] "25E / 4D as of a date BEFORE its introduction" → "did not exist… introduced [date]"
      (evals T1/T2 + CLI).
- [x] "25E / 4D as of today" → current text + introduction date (eval T3 + CLI).
- [x] Current-date / undated query answers from current, never superseded (10/10 evals unchanged).
- [x] Dated query on an UNMAPPED condition → RITA flags it can only show the CURRENT text and
      cannot confirm the historic position (honest caveat, not current-as-historic).
- Full eval: 13/13 decisions, 10/10 retrieval + citation, 3/3 temporal content, 0 hallucinations.

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
- [x] Verify gate (25E + 4D existence boundary) + temporal eval cases (T1–T3; 13/13 overall).
- [x] Scope note: unmapped condition at a past date → caveat "current text only, historic
      position not confirmed" (never presents current text as historic).
- [x] Flip public copy to present tense (present-tense "as of a past date", scope-honest).
- Deferred: ingest v2019/v2022 historic TEXT — only needed for text-CHANGE conditions (e.g.
  SLC 47 later); the existence-boundary demo doesn't need it (25E/4D didn't exist then).

### Build steps (text-CHANGE increment — Condition 28 Prepayment Meters) ✅ BUILT & VERIFIED
Data-scoping verdict: Condition 28's text changed **exactly once** in 2022→2025 — effective
**8 Nov 2023** (involuntary-PPM Code of Practice merged 28B into 28). The March 2024 marked-up
consolidation targets 28AD (Levelisation), and the May 2025 "extension to 2027" is a
statement-in-writing, not a text change — so v2022 + v2025 bracket the single change gap-free.
- [x] Verify single-change (not multi like SLC 47): confirmed via Ofgem modification history
      + a per-condition diff across held versions (v2022 stable from 2019; changed by v2025).
- [x] Version registry (`src/versions.py`): held consolidations v2022 + v2025, each with
      label/date/url/authority; **`CURRENT` derived as the latest** (removed the last hardcode).
- [x] Full v2022 ingestion (agreed): `extract_pages.py` → per-version caches; `chunk.py` tags
      every chunk `version_label/version_date/source_authority/url` and **namespaces ids by
      version** (`<label>__cond<n>_<idx>`); `embed.py` → 2133 chunks (1000 v2022 + 1133 v2025).
- [x] Temporal module: `TEXT_CHANGES` timeline for Condition 28 (contiguous segments →
      held version) + `version_for()` + `text_change_notes()`; existence-boundary path intact.
- [x] Version-scoped retrieval (`rag.py`): primary vector+BM25 filtered to the CURRENT version
      (undated behaviour byte-identical); a mapped text-change condition on a PAST date is
      SWAPPED to its resolved historic version and served WHOLE; context header + citations
      carry the consolidation date.
- [x] UI: prepayment before/after example (2021 vs 2024); caption widened to "how its wording
      has changed".
- [x] Evals: T4 (2021→v2022, pre-reform) + T5 (2024→v2025, post-reform); added a deterministic
      `expect_version` swap check. Full suite **15/15** (version-swap 2/2, 0 regressions).
- [x] Provenance: v2022 source URL recorded (public-only); v2019 noted held-not-ingested.
- Deferred: ingest v2019 (enables pre-2022 text-change conditions); multi-change conditions
  (SLC 47) once enough historic versions are held to keep every interval gap-free.

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

## Post-Phase-6 work log (2026-07-09 → 10)

### Embedder A/B — bge-small vs MiniLM (DONE — verdict: keep MiniLM) ✅
- Question: would a stronger embedder beat the ChromaDB default (`all-MiniLM-L6-v2`)?
  Tested `BAAI/bge-small-en-v1.5` (ONNX/fastembed, no PyTorch) over the 26 answer-cases,
  isolating the embedder (vector-only) from the pipeline (hybrid ± synonyms).
- **Verdict: not a net win — production stays on MiniLM hybrid+syn.** bge natively fixes the
  O4 vocabulary gap (21BA rank None→2 vector-only) but is worse as a raw embedder overall
  (recall@1 13 vs 17; P3 8→19), and MiniLM hybrid+syn is the ONLY config with zero recall@6
  misses. bge would fix an already-fixed problem at the cost of a full re-embed + heavier dep.
- Artefacts: `evals/embedder_ab.py` (hardened, resumable, 4 GB-safe), `evals/report.md`
  "Embedder A/B" section, `fastembed==0.8.0` pinned (eval-only). Branch `eval/embedder-ab-bge`
  (pushed, NOT merged to main — it's an experiment record, not an app change).
- Caveat: 26 cases / single run — 1–3 case differences are within noise.

### Live-deploy incident + guard (DONE) ✅
- Live crash on the deployed app (Streamlit Community Cloud): a **half-updated build** ran the
  new `app/main.py` (calling `history.compare()`) against a **stale `history` module** without
  it → AttributeError crashed the whole answer. Repo was consistent; it worked end-to-end
  locally. **Reboot fixed it.**
- Hardening: `app/main.py` now wraps the supplementary version-history panel in a per-entry
  try/except (skip + log to server logs, never crash the answer). Merged to `main` (c70bd49),
  redeployed. Rule: **reboot the app after any deploy** (auto-rebuild can half-update).

## NEXT — product-quality pass (AGREED, awaiting sign-off to start)
Goal Scott chose: **make the live product genuinely better** — measured, not by guessing.
- **Step 1 — Diagnose.** Build a realistic + adversarial question batch (lay phrasing, out-of-
  scope probes, temporal edges, multi-part conditions) beyond the ~30 tidy cases → ranked list
  of concrete failures tagged: retrieval miss / false refusal / hallucination / temporal caveat
  / genuinely out-of-scope.
- **Step 2 — Triage.** Pick the single dominant, fixable class.
- **Step 3 — Fix + verify.** Implement it; re-run for zero regressions (P1/P3 rigour).
- Optional parallel: privacy-safe capture of real demo questions (compounding loop).
- Candidate weaknesses to confirm with data (don't assume the winner): (a) scope refusals
  (electricity supply only); (b) temporal coverage gaps (only 5 conditions mapped); (c)
  retrieval misses on real phrasing; (d) refusal calibration.
- Constraint: safe on the 4 GB box — retrieval + modest API calls, **no re-embedding**.

## Phase 7 — Broad-query completeness (query planning / decomposition) — PROPOSED, pending sign-off

**Principle (Scott):** broad-query COMPLETENESS is an **accuracy requirement, equal weight to
precision**. A question like "what obligations do we have to vulnerable customers?" must surface
ALL the relevant obligations, not just the best-matching one. Mechanism = **automatic query
planning (decomposition)**. No user classification; a "comprehensive" override is optional only.

**Flow:**
1. **Plan** sub-queries from the question — a specific question yields 1 sub-query (itself); a
   broad one yields several (each a facet/obligation area).
2. **Retrieve** top-k per sub-query (existing hybrid: vector + BM25 + expansion), against the
   condition/section-tagged chunks.
3. **Union + de-duplicate** the retrieved chunks (by chunk id; keep best rank across sub-queries).
4. **Synthesize ONE grounded answer, grouped by obligation**, each point cited to source + section.
5. **Refuse** when no adequate match; otherwise add an **honesty line** that the answer reflects the
   retrieved sections and may not be exhaustive.

**Requirements this drives:**
- Chunk metadata carries condition/section for grouping + citation — **ALREADY MET**
  (`condition`, `condition_title`, `section` on every chunk). **No re-chunk / re-embed needed.**
- Evals must include **broad-query cases that measure RECALL** (did it surface all expected
  obligations?), not just precision on narrow queries — plus a precision/no-regression guard on
  narrow queries (decomposition must not degrade them).

**Design decisions — recommended resolutions (confirm/adjust before build):**
- **Planner = one LLM call** returning 1..N sub-queries (structured output). For narrow questions
  it returns just the original → no behaviour change. (Alt: heuristic gate — rejected as brittle.)
  Open: planner model (Opus vs cheaper Haiku for the plan step) — recommend measure, start Opus.
- **Cap sub-queries** (recommend ≤ 6) and **cap total unique chunks** fed to synthesis (recommend
  ~30–40, prioritised by best cross-sub-query score) — bounds cost/latency + precision drift.
- **Retrieval per sub-query** reuses the existing hybrid retriever untouched; union by chunk id;
  whole-condition / neighbour expansion applied AFTER union on survivors.
- **Synthesis** = grouped-by-obligation structured output (list of {obligation, detail,
  citations[]}); keep refusal + add non-exhaustiveness honesty line. UI renders grouped.
- **Temporal composes:** decomposition runs inside the resolved version scope (as-of date); the
  history panel is computed over the union of cited conditions (dedup + cap panels).
- **Refusal:** refuse only when the UNION is empty/inadequate; partial coverage → answer the
  covered obligations + the honesty caveat (the recall ceiling is stated, not hidden).

**Risks / guardrails:**
- Over-decomposition → precision drift / marginally-related conditions. Guard: cap sub-queries +
  chunk budget; synthesis stays grounded (assert only what's supported) so over-retrieval ≠
  hallucination.
- Cost/latency rise on broad queries (extra plan call + bigger synthesis context). Guard: caps +
  measure cost per broad query; consider Haiku planner.
- Narrow-query regression. Guard: eval precision/no-regression on the existing cases.

**Measure-first integration (reconciles with the quality-pass discipline):**
- Step 0 = **baseline**: add a handful of broad-query cases with hand-curated expected-condition
  sets and measure CURRENT recall (expected to be low) BEFORE building — so the fix is measured,
  not assumed. Then implement, then re-measure recall gain + precision/no-regression.

**Deferred (unchanged):** gas corpus; broader industry codes; the optional user "comprehensive"
override (automatic planner handles breadth; manual toggle is a later nice-to-have).

**Decisions SIGNED OFF (2026-07-10):**
- Planner = **corpus-aware** (wide-net retrieve → LLM selects relevant candidate conditions from
  their titles → focused sub-query per selected area → deep retrieve each). NOT blind decomposition.
- Grade on **condition recall + precision** (obligation grouping is a presentation layer; grading
  is deterministic on conditions).
- Caps accepted as tunable defaults: **≤ 6 sub-queries**, **~30–40 unique-chunk budget**.

**Still open (decide before/at build):** planner model (Opus vs cheaper Haiku for the plan step —
recommend start Opus, measure); exact grouped-obligation output schema + UI grouping.

### Anchor eval set — VERIFIED (Scott confirmed vs Ofgem, 2026-07-10)
Grading rule: **recall** = fraction of a query's CORE conditions surfaced; **precision** = surfacing
anything OUTSIDE Core ∪ Borderline is a miss (Borderline hits are "free", so reasonable breadth
isn't punished). This is now the signed-off seed for the `evals/` broad-query cases.
- **BQ1 "obligations to vulnerable customers"** — Core: 0, 26, 27, 27A, 28 · Borderline: 31G, 0A
- **BQ2 "billing obligations to domestic customers"** — Core: 21A, 21B, 21BA, 31H · Borderline: 22A, 31I, 27
- **BQ3 "what must we do when installing a smart meter?"** (cap stress-test) — Core: 39, 40, 41, 45 · Borderline: 42, 46, 47, 51
- **BQ4 "obligations before disconnecting a customer for debt"** — Core: 27, 27A, 28 · Borderline: 26, 0
- **BQ5 (NARROW CONTROL) "maximum back-billing period for domestic customers?"** — Core: 21BA · Borderline: (none).
  Proves decomposition yields **1 sub-query (itself)** and does NOT over-broaden or regress narrow queries.
