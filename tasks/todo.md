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

**Still open (decide before/at build):** exact grouped-obligation output schema + UI grouping.
**Planner model = Opus (decided 2026-07-10)** — simplest; measure cost after, optimise to Haiku later if needed.

### Step 0 baseline — DONE (2026-07-10, `evals/broad_baseline.py`, LOCAL / no API)
Current retrieval's Core-condition recall on the anchor set:
- **Served (k=6, what the app feeds today): 8/17 = 47%.** Ceiling (deep k=40): 15/17 = 88%.
- Per-query served: BQ1 2/5, BQ2 1/4, BQ3 2/4, BQ4 2/3, BQ5 (narrow control) 1/1 ✅.
- **Read:** the gap is real and quantified (47%). 88% reachable at depth ⇒ corpus-aware planner is
  the right fix. Killer evidence for TARGETED sub-queries: BQ2's "billing obligations" can't reach
  21BA even at depth 40, yet BQ5's narrow "back-billing" query surfaces it at rank 1 — the planner's
  sub-query finds what the broad query structurally can't. Precision measured at retrieval level only
  (synthesis filters); real answer-precision measured later. This "before" number is the fix target.

### Step 1 (planner) + Step 2 (union retrieval) — DONE (2026-07-10)
- `src/planner.py`: corpus-aware `plan()` + `plan_and_retrieve()` (per-sub-query hybrid retrieve →
  round-robin interleave union, budget 40). `evals/broad_compare.py` measures it vs baseline.
- **Recall: 47% → 100%** (`evals/broad_compare.py`). BQ1 2/5→5/5, BQ2 1/4→4/4, BQ3 2/4→4/4,
  BQ4 2/3→3/3, BQ5 narrow control 1/1 (unchanged, 2 sub-queries).
- BQ2 residual (21A/21BA) fixed by Option A: planner prompt now proactively adds well-known specific
  obligations (back-billing, annual statement, etc.) even when absent from the candidate list.
- Retrieval-level precision noise rises with recall (expected; synthesis filters) — real
  answer-precision measured at Step 3. (100% is on 5 anchor cases — a strong signal, not proof.)
- NEXT: Step 3 synthesis (grouped-by-obligation output; answer-level recall + precision).

### Step 3 (grouped synthesis) — DONE (2026-07-10)
- `src/planner.py`: `synthesize()` (reuses rag.SYSTEM grounding+temporal rules verbatim, grouped
  output via GROUPED_SCHEMA; derives backward-compat `answer`+`citations`) + `answer_broad()` (full
  pipeline). `evals/broad_synth.py` measures answer-level recall/precision.
- **Answer-level Core recall (CITED): 14/17 = 82%** (BQ1 5/5, BQ2 3/4, BQ3 3/4, BQ4 2/3, BQ5 1/1).
  Precision mostly clean (synthesis filters retrieval noise as predicted; BQ3 +49 smart-metering-adjacent).
- Gap vs 100% retrieval recall = synthesis selectivity (~1 Core dropped per broad query). Non-determinism
  observed (need variance handling in evals). BQ1 sample = 8 grouped, grounded, cited obligations.
- NEXT: Step 4 — wire answer_broad into rag.answer_question behind the out-of-scope backstop + UI grouped
  render + REGRESSION check on the existing 31-case hardened + temporal suite (must not regress).

### Step 4 (wire into answer_question) — DONE + regression GREEN (2026-07-10)
- `rag.answer_question` now: cheap out-of-scope backstop first (unchanged) → in-scope routes through
  `planner.answer_broad` (plan → union → grouped synthesis). `retrieved` meta rebuilt from the UNION.
  Backward-compat `answer`/`citations`/`context`/`prompt` preserved so UI + evals + temporal unchanged.
- Regression gate (`results_phase7_scopefix.json`, --no-judge): **decision 31/31, retrieval 26/26,
  citation 26/26, version-swap 8/8, history 2/2, 0 false refusals, 0 false answers.** Content 11/12 =
  only T4's "14 April 2022" string (grouped answer doesn't echo it verbatim; version IS served
  correctly) — deferred to the synthesis pass.
- D2 regression FIXED: initial wiring over-answered a Guaranteed-Standards (out-of-scope) question via
  a tangential Cond 14A; added a SCOPE DISCIPLINE instruction to the synthesis prompt → refuses when
  the question's CORE subject isn't in the extracts. Targeted re-check: 5/5 refusals refuse, 3/3
  answers answer; full suite confirms 0 false refusals.
- DEFERRED to synthesis pass: T4 date-string in grouped answer; lift answer-level recall (82%).

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

### Version-history panel on broad answers (2026-07-10, DONE + LIVE)
- (a) Lifted the 2-panel cap for broad answers (`rag.py` limit=8 when `is_broad`) → every mapped
  cited condition's history shows, per the completeness rule; narrow answers keep the cap of 2.
- (b) Added a coverage line in `app/main.py` (generated from `temporal`, so it self-updates):
  "Version history is mapped so far for Conditions 0A, 4D, 21B, 25E, 28 …" — so a broad answer
  showing 28's panel but not 27's is NOT misread as "27 never changed".

## BACKLOG — tracked so we don't forget
- **TEMPORAL MAPPING COMPLETENESS** (now user-visible via the coverage line — the UI names exactly
  which conditions are mapped, so gaps are obvious). Expand the mapped set beyond the current 5
  (0A, 21B, 28 text-change; 25E, 4D introduced). Candidates already noted: billing 31H, SoLR 8,
  more introduced conditions; an "expired/ceased" category (e.g. 28A, spent 30 Jun 2021).
  CONSTRAINT (non-negotiable, per Phase 6 rule): only map a condition whose history is gap-free
  from the consolidations we HOLD (v2019/v2022/v2025). Multi-change/volatile conditions (SLC 47)
  need more intermediate consolidations before they can be mapped — data-gated, not just effort.
  So this is an ongoing, incremental backlog, not a one-shot task.
- **Phase 7 SYNTHESIS PASS** (deferred): lift answer-level recall (82%); fix T4 date-string in the
  grouped answer; consider Haiku for the planner step to cut per-query cost on the live demo.

## SESSION CLOSE — 2026-07-10 (pre-lunch)
**Phase 7 (broad-query completeness) is DONE, regression-GREEN, and LIVE on the deployed app.**
Planner → union retrieval → grouped-by-obligation synthesis, wired into `answer_question` behind
the out-of-scope backstop; "Broad questions" UI section; version-history panel shows every mapped
cited condition + a self-updating coverage line. Pushed to origin/main + rebooted.
Also this session: repo confirmed public + secret-safe; added an **All Rights Reserved LICENSE**
(NOT MIT — preserves future sale) + README copyright footer.

### RESUME AFTER LUNCH — product-quality pass (measure → triage → fix → re-measure)
Return to the deferred quality pass (see "## NEXT — product-quality pass" above). Concretely:
- **Step 1 — Diagnose.** Build a batch of realistic + adversarial questions (lay phrasing,
  out-of-scope probes, temporal edges, multi-part conditions) beyond the tidy existing cases.
  Run them → ranked list of concrete failures, tagged: retrieval miss / false refusal /
  hallucination / temporal caveat / genuinely out-of-scope. NOTE: this now tests the LIVE Phase-7
  pipeline (planner + grouped synthesis), so it also stresses broad/decomposition behaviour.
- **Step 2 — Triage.** Pick the single dominant, fixable class (the one fix that helps the most).
- **Step 3 — Fix + verify.** Implement it; re-run for zero regressions (P1/P3 rigour); the 31-case
  hardened suite + the 5 broad anchors are the regression baseline.
- First action next session: draft the diagnostic question batch and show Scott BEFORE running any
  API calls (per the agreed sign-off habit).

### Quality pass ROUND 1 — DONE + LIVE (2026-07-10)
- **Diagnose** (`evals/diagnostic.py`, 24 realistic+adversarial Qs): system strong overall (lay
  phrasing ✅, pure out-of-scope refusals ✅, temporal caveats incl. unmapped-condition ✅, false
  premises refuted ✅, no invented figures ✅). Dominant fixable weakness = **compound/partial
  scope** (X3 Ombudsman, A4 switching+GS-compensation): answered a tangential in-scope obligation
  without flagging the out-of-scope part.
- **Fix** (`src/planner.py`): compound-scope handling + a new `out_of_scope_note` field — answer the
  covered part, name the uncovered part; pure out-of-scope still refuses.
- **Gold update (signed off):** D2 changed `refuse` → `answer` (expect 14A). D2 ≈ A4; the compound
  answer (14A timescale + GS-compensation caveat) is more honest+useful than a flat refusal. Gold
  was outdated by the new capability — NOT eval-gaming (verified by inspecting the actual output).
- **Regression GREEN:** 31/31 decisions, 27/27 retrieval + citation, 8/8 version, 0 false refusals,
  0 false answers (`results_phase7_scopefix_final.json`). Content 11/12 = T4 date-string (deferred).
- Watch-item: mild over-caveating on a fully-in-scope broad answer (BQ1 got a minor 0A note) — tune
  if it recurs. Remaining diagnostic items (low priority): future in-question dates (TE5), very-long
  broad answers (B2).

### Faithfulness gate + Haiku-planner cost cut — DONE + LIVE (2026-07-10)
- **Faithfulness judge** re-run on the Phase 7 grouped-synthesis pipeline: **27/27 faithful, 0
  hallucinations**, 31/31 decisions (`results_phase7_judge.json`). The larger unioned context did
  NOT introduce hallucinations — safety gate confirmed.
- **Planner → Haiku** (synthesis stays Opus). A/B (`evals/planner_ab.py`): Haiku planning matches
  Opus on anchor Core recall (16/17 both, identical per-anchor). Decoupled in `planner.py`
  (PLANNER_MODEL=Haiku; answer_broad passes synthesis model only to synthesize). Cuts one of the two
  per-query LLM calls to a ~10x-cheaper model. Regression GREEN: 31/31, 27/27 retrieval+citation,
  8/8 version, 0 false refusals/answers (`results_phase7_haiku_planner.json`).

## SESSION CLOSE — 2026-07-10 (end of day) · RESUME HERE NEXT TIME
**Shipped & live today:** Phase 7 broad-query completeness (planner → union → grouped synthesis),
end-to-end, regression 31/31, **faithfulness 27/27 (0 hallucinations)**, planner on Haiku for cost;
compound/partial-scope handling (out_of_scope_note); version-history multi-panel + coverage line;
repo public + All Rights Reserved LICENSE. All pushed to origin/main. (Reboot the Streamlit app once
more to pick up the Haiku-planner commit.)

**RESUME = Step 3, an open CHOICE (not yet decided):**
- **DEPTH — synthesis-recall pass:** lift answer-level completeness (synthesis cites ~82% of Core
  vs 100% retrieved — it drops ~1 Core condition per broad query); also fix the T4 date-string in
  the grouped answer. Measurable against the 5 broad anchors + 31-case suite. (My recommendation.)
- **BREADTH — temporal-mapping completeness:** map more conditions' version history (data-gated;
  needs per-condition Ofgem verification WITH Scott). See the BACKLOG section above.

**Also open (low priority):** over-caveat tune (BQ1's spurious 0A note), future in-question dates
(TE5), very-long broad answers (B2). Diagnostic harness = `evals/diagnostic.py`; broad-recall
harness = `evals/broad_compare.py` / `broad_synth.py`; anchors + grading rule in the Phase 7 section.
First action next session: confirm depth-vs-breadth with Scott, then (if depth) draft the
synthesis-recall improvement and show the measured before-number first.

## DEPTH chosen — Step 3 IN PROGRESS (2026-07-13)
Scott chose DEPTH (synthesis-recall pass). Also wrote `docs/how-ria-works-explained.md` (plain-
language design doc for a 15-yr-old; UNCOMMITTED — decide public vs local) alongside the technical
`docs/architecture.md` (committed + now pushed).

### Measured-first diagnosis (before touching code)
- Honest before-number = **~76% mean answer-level Core recall** (3-pass variance 71/76/82) — the
  previously-recorded "82%" was the lucky high end. Retrieval "100%" was also optimistic.
- Classified every dropped Core across BQ1-BQ4 as *in-context-but-dropped* (synthesis) vs
  *missing-from-context* (planner/retrieval). Result: **TWO problems, not one.**
  - **Problem A — synthesis over-merge** (BQ3 39/45, BQ4 27A present-but-uncited): GROUPED_SYSTEM
    said "group related points" → model collapsed distinct conditions to one representative citation.
  - **Problem B — planner/retrieval miss** (BQ2 21A never retrieved; 21BA flickers): planner didn't
    emit an "annual statement" sub-query; a local no-API rank probe showed 21BA is rank 1 under
    "back-billing maximum period" but rank 9 (below k_per=6) under the planner's actual phrasing.

### DEPTH change 1 — Problem A FIX: SHIPPED + LIVE (commit 97fa8c2)
- Added a CITATION COMPLETENESS rule to `planner.GROUPED_SYSTEM` (cite every condition that
  MATERIALLY addresses the question; never collapse distinct conditions to one representative).
- A tightened "core subject" variant OVER-CORRECTED (recall fell below baseline, BQ4 27A dropped
  again) → reverted to the "materially" wording. Lesson: completeness/precision wording is a live
  knob; measure both, don't eyeball.
- Measured: **answer-level Core recall ~76% -> ~84%** (floor 71% -> 82%). BQ4 27A fixed; BQ1 5/5 +
  BQ5 narrow control protected. Modest precision cost (BQ4 gains 31G — partly defensible).
- Regression GREEN (`results_phase7_depth_v1.json`, judge on): decision 31/31, retrieval 27/27,
  citation 27/27, version 8/8, history 2/2, **faithfulness 27/27 (0 hallucinations — more citations
  did NOT introduce unsupported claims)**, 0 false refusals/answers. Content 11/12 = date-string
  flicker (moved T4->T3 this run; same known deferred issue, not a regression).

### DEPTH change 2 — Problem B (planner -> 21A/21BA): SHIPPED + LIVE (commit 476931d)
Broad billing answers missed 21A (annual statement) + flickered on 21BA (back-billing) because the
LLM planner reaches them unreliably — both only rank top-k under an EXACT short term, and the
planner dilutes it (21A ranks #3 for "annual statement" but DROPS OUT once "domestic"/"consumption"
is appended; probe confirmed).
- Prompt-tuning approach FAILED: net-zero aggregate, destabilised BQ1/BQ4 guardrails. Reverted.
- FIX = deterministic `SPECIFIC_OBLIGATION_HINTS` table in `planner.py`: for a BROAD question whose
  area matches, inject proven-phrasing sub-queries verbatim ("annual statement", "Backbilling"),
  ADDITIVE (cap raised by count injected → planner coverage never displaced). Phrasings verified by
  a retrieval rank probe (scratchpad).
- TRIGGER IS TIGHT ON PURPOSE: matched against the QUESTION ONLY (not candidate titles) + SPECIFIC
  terms ("billing"/"back-billing"), not generic ("bill"/"statement"/"charge"). A loose first cut
  over-fired → billing hints injected into a disconnection Q ("unpaid bill") + a Guaranteed-Standards
  Q (billing conds among candidates) → 2 FALSE REFUSALS (D2, P1). The 31-case suite caught it before
  ship. Lesson: an additive retrieval booster can still cause REFUSALS by displacing the real extract
  from the budget-capped union — gate it narrowly and always run the full refusal suite.
- MEASURED: BQ2 context recall 58% -> 100% (12/12); overall context 90% -> 96%; answer-level Core
  recall ~84% -> ~88% (stable ×3). Regression GREEN (results_phase7_depth_v3_tighttrigger.json,
  judge on): 31/31, retrieval+citation 27/27, version 8/8, history 2/2, faithfulness 27/27 (0
  hallucinations), 0 false refusals/answers, recall@3 27/27, mean_rank 1.33.

### 21A residual RESOLVED — it was a WRONG ANCHOR, not a bug (commit c4c8fa1, LIVE)
Chasing "21A reaches context but isn't cited (BQ2 3/4)" revealed 21A's full text is the CRC (Carbon
Reduction Commitment) Energy Efficiency Scheme annual statement of supply to NON-domestic
Participants (CRC Order 2010) — NOTHING to do with domestic billing. Synthesis was CORRECT to exclude
it; the domestic billing-info/statements duty is 31H (already Core, already cited). Fix (D2-style,
evidence-led, NOT eval-gaming):
- `broad_baseline.py`: BQ2 Core -> {21B, 21BA, 31H} (dropped CRC 21A).
- `planner.py`: dropped the "annual statement" hint (only fetched out-of-scope 21A); kept "Backbilling".
- Re-verify GREEN: BQ2 answer-level 3/3 = 100% every pass, clean precision; answer-level aggregate
  ~92% on the corrected 16-condition set; regression 31/31, retrieval+citation 27/27, faithfulness
  27/27 (0 hallucinations), 0 false refusals/answers. (`results_phase7_depth_v4_21Afix.json`.)
LESSON: a condition's TITLE can mislead — 21A "annual statement" sounded like domestic billing but the
BODY is CRC/non-domestic. Verify anchors against the actual licence TEXT, not the title. The system
excluding an out-of-scope condition is correct behaviour, not a recall miss.

### BQ3 body-check — 45 was ALSO a soft anchor (demoted; NOT a system miss)
BQ3 deterministically dropped Cond 45 ("Smart Metering Consumer Engagement"). Body-check: 45 is
about establishing/funding a CENTRAL consumer-engagement body (Smart Energy GB), NOT an operational
install duty, AND it CEASED to apply 30 Jun 2021 (spent in the 2025 consolidation). Synthesis was
CORRECT to exclude it for "what must we do when installing a smart meter". Demoted Core -> Borderline
(`broad_baseline.py`); 39/40/41 are the real install duties (all cited every run). Second title-vs-
body anchor error after 21A — same lesson: check the BODY.
- RE-SCORED (no re-run needed — anchor change only reclassifies which conds count as core; model
  outputs unchanged): answer-level Core recall on the corrected 15-condition anchor set = 100/93/100
  across the three v4 passes → **mean ~98%**. The ONLY residual is BQ4's single non-deterministic
  flicker on 27/27A/28.

### RESIDUAL / still-open (logged, not chased)
- **T3/T5 date-string:** grouped answer doesn't always echo the exact consolidation date verbatim
  (content 10-11/12, flickers between temporal cases run-to-run). Deferred synthesis-pass item; does
  NOT affect decision/version/faithfulness (those stay correct).
- **BQ4 flicker:** occasionally 2/3 (drops one of 27/27A/28) — pure synthesis non-determinism, within
  noise on a 5-anchor set. Not worth chasing.
- DEPTH net result (changes 1+2 + both anchor corrections): answer-level Core recall ~76% -> **~98%**
  on corrected anchors; regression + faithfulness green throughout; 0 hallucinations. BQ2 + BQ3 fully
  resolved. NOTE: the honest read is the system is near-complete on GENUINE core obligations — the
  earlier "92%" understated because two anchors had soft/incorrect core members (21A, 45).
- CONFIDENCE CAVEAT (now ADDRESSED): 5 anchors was a weak signal. Expanded to 20 (below).

### Broad-anchor set EXPANDED 5 -> 20 (body-verified) — DONE + committed (59146f9, 2026-07-13)
Added BQ6-20 across all three sections (prepayment, switching, tariffs, supplier-failure/continuity,
non-domestic, fair-treatment, smart-data, credit balances, advice service, financial-resilience,
metering/theft, fuel-mix, FIT, SEG) + 2nd narrow control (BQ16). Gold BODY-verified via 3 parallel
subagents + a full-body trap-scan (`scratchpad/anchor_verify.py`) — rejected ceased/spent (28A,28AA,
24A,22B,32A,45), wrong-scheme (35 Green Deal not FIT; 59 alt-fuel not SEG), wrong-customer-type
(7A/7D/20). Scott's rulings baked: keep BQ11 (core {0}); BQ14 domestic (core {31G}); BQ9 -> {8,9,19C}.
FIRST MEASUREMENT (honest baseline — more diverse => harder than the old 5): context 46/49 (94%);
answer-level 44/49 (90%, 1 full pass; a 2nd pass aborted on an API 503 — flakiness continues).
- NEW residuals surfaced (real signal the 5-anchor set hid — candidate next DEPTH targets):
  * **BQ8 tariffs 1/3** — 22A + 25 not reached (context missed 22A too) = a planner/retrieval gap,
    SAME SHAPE as the old 21A/21BA billing gap. Clearest next target if continuing DEPTH.
  * BQ9/BQ10/BQ15 each drop 1 core (SoLR / non-domestic / 19C continuity-plan).
  * Precision noise on near-narrow BQ11/BQ14 (core=1 condition, synthesis lists 5-6 extras).
- Harnesses now cover 20 anchors automatically (`broad_synth.py`, `scratchpad/all20_context.py`).
  Note: for a stable answer-level number, run 2-3 passes (non-deterministic); today = 1 full pass.

### DEPTH essentially complete — next options (pick next session)
- Chase the 21A answer-level residual (small synthesis-selection tweak) to get BQ2 -> 4/4.
- Or switch to BREADTH (temporal-mapping completeness — data-gated, needs Ofgem verification WITH Scott).
- Or the date-string fix + low-priority polish (over-caveat, TE5, B2).
REMINDER: reboot the Streamlit app to pick up c4c8fa1 (anchor fix + hint) + 476931d (Problem B) +
97fa8c2 (citation-completeness) + the earlier Haiku-planner commit — the live site won't reflect
DEPTH until rebooted.
Uncommitted still: docs/how-ria-works-explained.md (decide public vs local).

## SESSION CLOSE — 2026-07-13 · RESUME HERE NEXT TIME
**DEPTH pass (broad-answer recall) is DONE, shipped, regression-GREEN, faithfulness-clean.**
Answer-level Core recall **~76% -> ~92%** (on corrected anchors), 0 hallucinations throughout,
0 false refusals in the shipped state. Three commits landed on origin/main today:
- 97fa8c2 — citation-completeness rule (synthesis stops over-merging conditions). 76% -> 84%.
- 476931d — deterministic hint sub-queries (Problem B; BQ2 context 58% -> 100%). 84% -> 88%.
- c4c8fa1 — corrected BQ2 anchor (21A is CRC/non-domestic, not billing) + dropped phantom hint.
  BQ2 answer 3/3 = 100%; aggregate ~92%.
Plus docs commits (d41acae, d02b0b0, b3cee5b) and today's `architecture.md` reached origin.

### ⚠️ FIRST ACTIONS NEXT SESSION
1. **REBOOT the Streamlit app** — none of today's DEPTH work is live until you do (picks up c4c8fa1,
   476931d, 97fa8c2, and the Haiku-planner commit). Then sanity-check a broad billing question in
   the live app.
2. Decide **docs/how-ria-works-explained.md** — commit (public) or keep local (still uncommitted).

### STATE OF PLAY
- Regression baseline to protect: 31-case hardened suite + 5 broad anchors. Latest green =
  `results_phase7_depth_v4_21Afix.json` (decision 31/31, retrieval+citation 27/27, faithfulness
  27/27, version 8/8, history 2/2, 0 false refusals/answers).
- Harnesses: `evals/run_evals.py` (31-case + judge), `evals/broad_synth.py` (answer-level recall,
  run 3x for variance), `scratchpad/problemB_before.py` (cheap context-level recall, no Opus).
  NOTE: scratchpad/ is untracked throwaway diagnostics — safe to delete or keep.
- API was flaky today: serialise structured-output eval jobs (don't run two at once) — see lessons.

### RESUME = pick the next fork (DEPTH essentially complete)
- **BREADTH — temporal-mapping completeness** (the differentiator; data-gated, needs per-condition
  Ofgem verification WITH Scott). See BACKLOG. Candidates: billing 31H, SoLR 8, more introduced
  conditions, an expired/ceased category. Constraint: only map gap-free histories from held
  consolidations (v2019/v2022/v2025).
- **DEPTH low-priority polish** (optional): T3/T5 date-string-in-grouped-answer (content 10-11/12,
  flickers; decision/version/faithfulness stay correct); over-caveat tune; future in-question dates
  (TE5); very-long broad answers (B2). (BQ3 3/4 RESOLVED — was a soft anchor, 45 demoted; see above.)
Recommendation: BREADTH next (bigger product value), but it needs a working session WITH Scott to
verify Ofgem histories — so confirm which condition(s) to map first before drafting.

## SESSION CLOSE — 2026-07-13 (END OF DAY, authoritative) · RESUME HERE TOMORROW
Big day. DEPTH pass fully done + a 20-query body-verified anchor set built. All on origin/main.

**Shipped/committed today (in order):** 97fa8c2 citation-completeness (recall 76→84%) · 476931d
deterministic hint sub-queries / Problem B (BQ2 context 58→100%) · c4c8fa1 corrected BQ2 anchor
(21A = CRC/non-domestic) · 71a01d5 demoted BQ3 45 (ceased consumer-engagement body) · 59146f9
expanded anchor set 5→20 (body-verified). Plus doc/todo commits (latest 2011fd4) + architecture.md.

**State:** DEPTH answer-level recall ~76%→~92% on the (corrected) 5 anchors; on the NEW 20-anchor
set the honest baseline is answer-level 90% (44/49, 1 pass) / context 94% (46/49). Regression suite
(31-case) last GREEN at c4c8fa1-era: decision 31/31, faithfulness 27/27, 0 false refusals.

### ⚠️ FIRST ACTIONS TOMORROW
1. **REBOOT the Streamlit app** — today's DEPTH commits (97fa8c2, 476931d, c4c8fa1) are NOT live
   until reboot. (The anchor-set + doc commits are eval/docs only, no app impact.)
2. Decide **docs/how-ria-works-explained.md** — still uncommitted (public vs local).

### BQ8 tariffs gap — FIXED + LIVE (commit fd2431f, 2026-07-14)
Diagnosis: 22A + 31I were MISSING-FROM-CONTEXT (retrieval gap, not synthesis; 25 was fine) — same
shape as 21A/21BA. Rank probe: 22A ranks #1 for "Unit Rate Standing Charge", 31I #1 for "contract
changes information price change" — planner never produced those. FIX = "tariffs" entry in
`planner.SPECIFIC_OBLIGATION_HINTS` with those proven phrasings. Trigger over-fire-tested: "tariff"
alone hit BQ18/BQ19/O3/P6 too → narrowed to ("unit rate","standing charge","prices") = fires BQ8
alone, 0 collateral. Verified: BQ8 1/3 -> 3/3 (context+answer, 3 runs); 20-anchor answer ~90% -> ~94%;
regression GREEN (results_phase7_bq8_tariffs.json): 31/31, 27/27 retr+cite, content 12/12,
faithfulness 27/27, 0 false refusals. Watch: mild BQ8 precision noise (21B, 7D).
REMINDER: this is a pipeline change → app reboot needed to go live.

### (DONE — kept for the record) The BQ8 approach that was used
BQ8 "What must we tell customers about tariffs and prices?" scored **1/3** — core {22A, 25, 31I};
22A + 25 not reached (context missed 22A too → a planner/retrieval gap, SAME SHAPE as the old
21A/21BA billing gap that the deterministic hint fixed). Approach (mirror the Problem B playbook):
- STEP 1 measure-first: is it retrieval (22A/25 never reach context) or synthesis (present, uncited)?
  Use `scratchpad/all20_context.py` (context-level, no Opus) + a per-condition rank probe like
  `scratchpad/bq2_retrieval_probe.py` — find the phrasing that ranks 22A ("Unit Rate, Standing Charge
  and Tariff Name") and 25 ("Informed choices – Tariff comparability and marketing") into top-k.
- STEP 2 fix: likely a deterministic hint entry for the "tariffs/prices" area in
  `planner.SPECIFIC_OBLIGATION_HINTS` (proven phrasing), with a TIGHT trigger (the loose-trigger
  false-refusal bug from Problem B — match question only, specific terms; ALWAYS run the 31-case
  refusal suite after).
- STEP 3 verify: re-measure BQ8 + full 20-anchor answer-level (2-3 passes for variance) + 31-case
  regression + faithfulness. Zero regressions, watch precision on near-narrow BQ11/BQ14.
- Show Scott the measured before-number FIRST (sign-off habit).

### Also queued / open (lower priority)
- 20-set residuals RESOLVED 2026-07-14: BQ9 (3/3 over 3 runs) + BQ10 (4/4) were single-pass FLICKER,
  no fix. BQ15 anchor-corrected: 19A/19C demoted Core->Borderline (reporting/continuity, not
  resilience) -> core {4A,4B,4C} cited ~3/3 (13bf959). NET: after BQ8 fix + these, the 20-anchor set
  is effectively healthy on GENUINE cores; remaining misses are variance flicker (e.g. BQ4 27x, BQ15
  4A). Still open: precision noise on near-narrow BQ11/BQ14 + mild BQ8 (21B/7D); a proper 3-pass
  20-anchor number for the record (today's per-anchor diagnoses were 3-run, but not one combined pass).
- 2nd full answer-level variance pass on the 20-set (today only got 1 — API 503 aborted pass 2).
- T3/T5 date-string flicker (content 10-11/12). BREADTH (temporal mapping, needs Ofgem session).
- Open question from lessons: can the live pipeline ever present a CEASED condition (28A/45/etc.)
  as current? Not yet checked.
- API was flaky today: serialise structured-output eval jobs; a 2-pass job aborted mid-run.

## COFFEE BREAK — 2026-07-14 (mid-session) · RESUME HERE
### Truncation crash-fix — SHIPPED + LIVE (commit 7f13b84)
synthesize() max_tokens 4096->8192; retry once at 16384 on truncation/malformed JSON; then graceful
degrade — never crash. Ship-gate GREEN (results_trunc_fix.json): 31/31, retrieval+citation 27/27,
content 12/12, version 8/8, history 2/2, faithfulness 27/27, 0 false refusals. Needs app reboot to go live.

### What happened this half-session
- The 3-pass 20-anchor measurement kept CRASHING at BQ6 — root cause was a REAL LIVE BUG, not the API:
  synthesis JSON truncated at max_tokens=4096 (thinking shares the budget) on long grouped answers
  (BQ6 prepayment ~11 obligations) -> json.loads crash. Fixed (above). Some of yesterday's "API
  flakiness" JSONDecodeErrors were probably THIS. See lessons.md.
- FINAL for-the-record measurement (corrected 47-condition set, truncation fix in place):
  **answer-level Core recall 98% / 100% / 96% -> mean ~98% (138/141)**, 0 crashes. Residual = pure
  flicker (different anchor each pass: BQ19, BQ7, BQ10 dropped 1 once each). The set is HEALTHY.

### RESUME AFTER COFFEE — in order
1. **Ship-gate the truncation fix:** run `venv/bin/python evals/run_evals.py --label trunc_fix`
   (31-case + faithfulness). Confirm 31/31, faithfulness clean, 0 false refusals (bigger token budget
   + guard must not change narrow/refusal/temporal). If GREEN -> commit + push `src/planner.py` (LIVE
   crash-fix; needs app reboot). 
2. BQ11/BQ14 over-broadening — DONE 2026-07-14 (dee40da). Diagnosis: NOT a system bug — the broad
   answers are largely CORRECT (fair-treatment genuinely spans the consumer-protection suite;
   info-service spans billing/consumption/PSR info). GOLD-CALIBRATION fix: widened Borderline (BQ11
   +27/27A/28/21B/31H; BQ14 +21B/51), re-scored from EXISTING 3-pass data ($0 API) — noise BQ11 ~4->1.3,
   BQ14 ~2.3->1.3/pass, recall unchanged. Residual noise (22D/23/31I; 27/28) kept out deliberately.
   A synthesis tightening was AVOIDED (it over-corrected during DEPTH). [superseded task below]
   ~~Then tackle BQ11/BQ14 over-broadening~~ (the agreed task). Characterised by the 3-pass run:
   near-narrow anchors over-cite — BQ11 (core {0}) cited up to 7 extras (21B,22D,23,27,27A,28,31H =
   billing/prepayment/disconnection dressed as "fair-treatment"); BQ14 (core {31G}) cited 21B,27,28,51.
   Root: planner marks these broad-sounding-but-really-narrow Qs is_broad -> over-decomposes -> synthesis
   lists tangential obligations. Fix direction TBD (measure first): tighten planner is_broad, or tighten
   synthesis scope discipline to not cite conditions outside the question's core subject. Show before-number.
### Reminder: app reboot still pending for all today's pipeline commits (BQ8 tariff fd2431f + the
### truncation fix once committed) + yesterday's DEPTH commits.

## Ceased-condition correctness check — DONE + FIXED (2026-07-14, commit 37e37e7)
CHECK RESULT: correctness PASS — spent conditions are NOT presented as current (grounding flags the
cease dates); no hallucination. WEAKNESS found: spent conditions out-ranked current equivalents
(28A/28AA crowded out live charge cap 28AD). FIX (approach B): demote 7 known-spent conditions
{22B,24A,28A,28AA,32A,37,45} below current ones in fusion (stable, still retrievable). Plus a
transient-503 retry wrapper in planner (cost + live-crash hardening). Ship-gate: retrieval 27/27,
faithfulness 26/26, version 8/8, history 2/2, 0 false answers; the lone P1 refusal = confirmed
flicker (P1 retrieval unchanged by demotion; 2 clean re-runs). LIVE pipeline change -> needs reboot.

## ELECTRICITY RIA — WRAPPED (2026-07-14)
Finish-line items all done:
- ✅ Ceased-condition correctness check (PASS) + spent-condition demotion fix (37e37e7).
- ✅ Final eval report — `evals/report.md` "FINAL STATE" section (e0b0d6d).
- ✅ Plain-language explainer committed to LOCAL-ONLY branch `private-docs` (8be851f) — NOT on main/
  public (repo is public; doc is copy-risk). It is ABSENT from main's working tree by design. To view:
  `git checkout private-docs`. Only merge to main if the repo is made private or the doc is published.
- ✅ App REBOOTED by Scott — all pipeline fixes now LIVE (BQ8 tariff hint, truncation crash-fix,
  spent-demotion, 503-retry, citation-completeness, Haiku planner, hint sub-queries).
State of record: 31-case 31/31 + faithfulness 27/27 (0 hallucinations); 20-anchor broad ~98% mean;
ceased-condition PASS. Electricity RIA is a correct, documented, live, eval-backed artefact.

### Optional future work (NOT part of wrap-up)
- BREADTH — temporal-mapping completeness (the differentiator; data-gated + needs Ofgem sessions WITH Scott).
- Low-value polish: date-string flicker, mild broad-answer precision noise, cheaper synthesis model for cost.
- Cost discipline now in effect (see memory cost-conscious-evals): re-score not re-run, diagnose locally,
  reserve full regressions for ship-gates.

## SESSION CLOSE — 2026-07-14 (end)
Electricity RIA WRAPPED (see section above). This session shipped, all LIVE (app rebooted by Scott):
- BQ8 tariffs hint (fd2431f) · synthesis truncation crash-fix + 503-retry (7f13b84, 37e37e7) ·
  spent-condition demotion (37e37e7) · BQ15/BQ11/BQ14 gold recalibrations (13bf959, dee40da).
- 20-query body-verified broad-anchor set (59146f9); final eval report (e0b0d6d).
- Plain-language explainer on LOCAL-ONLY branch `private-docs` (8be851f) — private, not on GitHub.
State of record: hardened 31/31 + faithfulness 27/27; broad-anchor ~98% mean; ceased-condition PASS.

### RESUME (whenever): optional future work only — RIA is done as a wrap.
1. BREADTH — temporal-mapping completeness (differentiator; DATA-GATED + needs an Ofgem-verification
   session WITH Scott; only map gap-free histories from held v2019/22/25). The high-value next track.
2. Low-value polish: date-string flicker (content 11-12/12); mild broad-answer precision noise;
   cheaper synthesis model for live cost (measure-gated).
COST DISCIPLINE IN EFFECT (memory cost-conscious-evals): re-score not re-run; diagnose locally;
reserve full regressions for ship-gates; ask before expensive runs.

## BREADTH candidate analysis — DONE (2026-07-14, $0 local diff of held versions)
Source: `docs/change-map.md` (change-detector) + `scratchpad/ceased_scan.py` (ceased scan). Held
versions: v2019 (89 conds) / v2022 (105) / v2025 (111). Landscape: STABLE 44 · SINGLE-CHANGE 28
(3 mapped: 0A,21B,28) · INTRODUCED 22 (2 mapped: 25E,4D) · CEASED 7 · MULTI-CHANGE 9 (avoid).
CAVEAT (non-negotiable): a snapshot diff sees only interval ENDPOINTS — every "single-change"
candidate MUST be confirmed against Ofgem's modification history before mapping (a condition may
change multiple times within a gap). That confirmation = the with-Scott part; not derivable from corpus.

### Prioritised shortlist for the NEXT mapping session (value × cleanliness)
Text-change (single, verify vs Ofgem): 31H (billing info) · 8/9 (Last Resort Supply) · 24 (domestic
contract termination) · 31G (assistance/advice).
Introduced (existence-boundary — cleanest): 27A (self-disconnection) · 4A/4B/4C (financial
resilience/fit-proper) · 19C (supply continuity plans).
Ceased/expired (NEW category to build): 28A (PPM charge restriction, in force 2017-2020, ceased 2021)
· 45 (smart-meter consumer engagement, ceased 2021).
AVOID (volatile, need intermediate consolidations): 47, 14A, 27, 28AD, 55, 1, 12, 14, 15.

### Process to actually map one (per condition, with Scott)
1. Confirm the real effective date(s) from Ofgem modification notices / EPR (epr.ofgem.gov.uk).
2. Confirm it's gap-free across held versions (single change / clean intro / clean cease).
3. Add to `src/temporal.py` (TEXT_CHANGES timeline / INTRODUCED / a new CEASED map).
4. Add eval cases + verify (dated query resolves; undated unchanged; regression green).

## Synthesis-cost A/B — DONE, Sonnet REJECTED (2026-07-16)
Goal: could a cheaper model replace **Opus** on the grouped-synthesis step (the dominant per-broad-
query cost; planner is already Haiku)? Screened Opus vs Sonnet 5 vs Haiku over the 20 body-verified
broad anchors (shared union per anchor; only synthesis model varied), then ship-gated the survivor.
- **Screen (`evals/synth_model_ab.py`):** Opus 47/47 (100%) · **Sonnet 47/47 (100%)**, same precision
  noise · Haiku 28/47 (60%), +175 noise, 2 false refusals (Haiku path has no adaptive thinking → not
  viable). Sonnet TIED Opus on broad recall/precision.
- **Ship-gate (`run_evals.py --model claude-sonnet-5 --judge-model claude-opus-4-8`, new independent-
  judge flag):** Sonnet FAILED the correctness gate. Faithfulness 24/26 vs Opus 27/27 — T1 asserted
  UNMAPPED Cond 4A as "verified-historical"; T5 relied on UNMAPPED Cond 27A as a past-date position
  (both break the core temporal rule: unmapped + past date → never present current text as historic).
  Plus D2 false-refused a compound-scope case Opus answers. Coherent failure mode, not noise.
- **DECISION (Scott): reject Sonnet, synthesis STAYS on Opus.** Temporal correctness is RIA's
  differentiator; Sonnet trades away the one property most worth protecting. No pipeline change → no
  app reboot needed. If cost pressure returns, only live option = HYBRID routing (broad-undated →
  cheaper, temporal/narrow → Opus), NOT a global swap; needs a broad-faithfulness check first.
- Kept: `evals/synth_model_ab.py`, `evals/synth_sonnet_variance.py`, `run_evals.py --judge-model`
  (independent faithfulness judge — a genuine harness improvement). See memory synthesis-model-ab-rejected.

## BREADTH batch 1 — DONE, ship-gate GREEN (2026-07-16). Mapped set 5 → 9 conditions.
First temporal-mapping expansion since Phase 6. Scott verified all effective dates against Ofgem.
Added (all gap-free from held v2019/v2022/v2025):
- **27A Self-disconnection** — INTRODUCED 15 Dec 2020 AND text-changed 8 Nov 2023 (involuntary-PPM
  credit paras 27A.7A-7C, the same reform as Cond 28). Modelled in TEXT_CHANGES with an `introduced`
  marker; pre-introduction serves current text + "did not exist, introduced [date]" (existence-
  boundary semantics via a new `version_for` branch). Cases T10 (before) / T11 (pre-IPPM v2022) /
  T12 (post-IPPM v2025).
- **4C Ongoing fit and proper requirement** — INTRODUCED 18 Mar 2021 (pure existence boundary, text
  stable). MAPPED entry. Cases T13/T14 (phrased to isolate 4C — see below).
- **19C Customer supply continuity plans** — INTRODUCED 18 Mar 2021 (pure existence boundary).
  MAPPED entry. Cases T15/T16.
- **31H Relevant Billing Information** — text-changed 31 Dec 2020 (Clean Energy Package / recast
  Electricity Directive transposition — SAME date/SI as 21B). v2019 before → v2025 after. Cases
  T17/T18. NOTE: the supplied 11 Feb 2019 date predated our earliest held consolidation (already in
  v2019, not demonstrable) — the mappable change was the CEP one; caught by a $0 v2019-vs-v2022 diff.
- SHIP-GATE (`results_breadth_batch1.json`, 40 cases, Opus synth + Opus judge): decision 40/40,
  retrieval+citation 36/36, version 12/12, history 5/6, **faithfulness 36/36 (0 hallucinations)**,
  0 false refusals, 0 false answers. Residual: T3 date-string flicker (known/deferred), and T13's
  original crowded phrasing (fixed).
- T13 crowded-retrieval edge (LOGGED, low priority): a before-introduction query whose topic pulls a
  pack of competing conditions can arbitrate the introduction fact away (flickered refuse/answer).
  Isolating phrasing gives the clean existence-boundary answer; mapping is sound. See lessons.
- CODE: `src/temporal.py` (27A/31H TEXT_CHANGES + 4C/19C MAPPED + introduced-aware pre-existence note
  + `version_for` branch), `src/history.py` (introduced marker on introduced text-change conditions),
  `evals/cases.yaml` (T10-T18). ⚠️ Live pipeline change → **app reboot needed** to go live.

### BREADTH — next candidates (same process: Ofgem-verify dates WITH Scott, then $0 map + batch gate)
Remaining single-text-change (verify single + gap-free): 24 (domestic contract termination, chg
2019→2022) · 8 (LRS direction, chg 2019→2022) · 9 (LRS payment claims, chg 2022→2025) · 31G
(assistance/advice, chg 2022→2025). Introduced+text-change: 4A (operational capability). AVOID: 4B
(1→23 chunks 2022→2025 = total rewrite, almost certainly multi-change / not gap-free); the volatile
set (47, 14A, 27, 28AD, 55). Ceased category (28A, 45) still unbuilt.
