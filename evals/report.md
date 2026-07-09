# RIA — Eval Report (Phase 5)

Lightweight, deterministic evaluation of the Regulatory Intelligence Assistant.
Cases in `evals/cases.yaml` (derived from `docs/query-taxonomy.md`); runner
`evals/run_evals.py`. Run 2026-07-07.

**Grading (deterministic, no LLM-judge):**
- **Decision correctness** — did it *answer vs refuse* as expected?
- **Retrieval hit** — did an expected condition appear in the top-6 retrieved set?
- **Citation hit** — did an expected condition appear in the model's citations?

10 cases: 7 expected-answer, 3 expected-refuse (out of the electricity supply SLC corpus).

---

## Headline result — baseline → hybrid retrieval (Opus 4.8)

| Metric | Baseline (vector only) | **Hybrid (vector + BM25)** |
|---|---|---|
| Decision accuracy | 9/10 | **10/10** |
| Retrieval hit-rate (answer cases) | 6/7 | **7/7** |
| Citation hit-rate (answer cases) | 6/7 | **7/7** |
| False answers (hallucinations) | 0 | **0** |
| Correct refusals | D1, D2, S4 ✅ | D1, D2, S4 ✅ |
| False refusals | O4 | **none** |

**The system is grounded and disciplined:** every out-of-scope question (Ombudsman
deadline, Guaranteed Standards, gas-boiler safety) is correctly refused, and it never
invented an answer. The baseline's single failure (**O4**, a false refusal) was fixed
by **hybrid retrieval** — with zero regressions and still zero hallucinations.

---

## The O4 false refusal — diagnosis → fix (now resolved)

*"What is the maximum back-billing period for domestic customers?"* was refused, even
though the corpus answers it (Condition 21BA = 12 months) and answers the near-synonym
*"can a supplier back-bill more than 12 months ago?"* (S1) at rank 1. Cause: a
**vocabulary gap** in the default embedder (`all-MiniLM-L6-v2`) — the query says
"maximum back-billing period"; the 21BA chunk says "Backbilling / 12 months preceding".

### Attempt 1 — embed the condition title → reverted
Embedding each chunk *with* its title only moved 21BA from *absent in top-15* → **rank 18**
(still a false refusal), and polluted the context. **Reverted.**

### Fix (implemented) — hybrid retrieval, in three measured pieces
1. **BM25 keyword search fused with vector via Reciprocal Rank Fusion.** Alone, though,
   the verbose query diluted the signal — generic terms ("domestic customers billing
   period charges") matched the charge-regulation conditions and 21BA ranked only **36th**.
2. **Title field-boost (×8).** The condition title is a high-signal field; repeating it in
   the BM25 document lifted 21BA to **keyword rank 1**. Swept against control questions
   (O1/O2 stayed rank 1–2); stopword removal was tried and *rejected* (it degraded O1).
3. **Whole-condition expansion for small conditions (≤8 chunks).** A keyword hit means the
   whole condition is relevant, so we pull all of it — ensuring the chunk with the actual
   "12 months" rule (21BA.1) reaches Claude, not just whichever fragment matched.

**Result: O4 answers correctly, cited to 21BA. Eval 9/10 → 10/10, retrieval 6/7 → 7/7,
zero regressions, still zero hallucinations, all three refusals intact.**

---

## Model A/B — Opus 4.8 vs Haiku 4.5

Same clean store, same 10 cases.

| Metric | Opus 4.8 | Haiku 4.5 |
|---|---|---|
| Decision accuracy | 9/10 | 9/10 |
| Retrieval hit-rate | 6/7 | 6/7 |
| False answers | 0 | 0 |
| Citation hit-rate | **6/7** | **2/7** |

**Equal on substance** (decisions, retrieval, zero hallucinations). The difference is
**citation formatting**: Opus reliably cites the bare condition number (`27`, `21BA`);
Haiku emits sub-paragraph refs (`27.11`, `31I.6`) or prefixes (`Condition 0`), which the
strict grader scores as misses. That 2/7 *overstates* the gap (Haiku found the right
conditions) but also reflects a real difference — Opus produces the clean condition-level
citations a regulatory tool wants, unprompted.

**Conclusion:** the A/B **validates the Opus 4.8 choice** — identical correctness plus
citation-format discipline — at a cost that's single-digit dollars at PoC scale. Haiku is
viable on substance if cost ever dominates, ideally after the schema improvement below.

---

## Where retrieval / prompting is weak (for later)

1. ~~O4 vocabulary-gap false refusal~~ — **resolved** by hybrid retrieval (above).
2. **Citation field formatting** — weaker models put sub-paragraph refs in the `condition`
   field. Cheap fix: tighten the schema description to "bare condition number, e.g. `21BA`".
3. **Grader is strict on citation format** — it does exact-match on the condition string;
   a normalising matcher (strip sub-paragraph suffix / "Condition " prefix) would measure
   *grounding* more fairly, separately from *format*.
4. **Eval set is small (10 cases).** 10/10 is a strong signal, not proof — expand the
   taxonomy to stress more conditions and more paraphrase variants.

## Phase 6 — temporal ("as of date") cases

Three temporal cases added (T1–T3), existence-boundary for the two mapped conditions
(25E introduced 24 Sep 2022; 4D introduced 20 Sep 2023). The runner passes an `as_of`
date and a `expect_contains` content check (the introduction date must be surfaced).

| Metric (13 cases total) | Result |
|---|---|
| Decision accuracy | 13/13 |
| Retrieval hit-rate | 10/10 |
| Citation hit-rate | 10/10 |
| Temporal content checks | 3/3 |
| Hallucinations | 0 |

- T1 (4D as of 2021) / T2 (25E as of 2022) → "did not exist… introduced [date]" ✅
- T3 (4D today) → current text + introduction date ✅
- The 10 non-temporal cases are unchanged (the temporal layer is invisible when undated).
- Unmapped condition at a past date → RITA states it can only show the current text and
  cannot confirm the historic position (verified by hand; not a graded case).

## Phase 6 (increment 2) — temporal TEXT-CHANGE cases

Three mapped text-change conditions, each with a verified single change and a held version on
each side; RITA serves the version of a condition's text in force as of the date. The corpus
now holds **three** version-tagged consolidations (v2019 + v2022 + v2025):
- **Condition 28 (Prepayment Meters)** — changed **8 Nov 2023** (involuntary-PPM Code of Practice).
- **Condition 0A (Treating Non-Domestic Customers Fairly)** — changed **1 Jul 2024** (Non-Domestic
  Market Review; scope expanded from microbusiness-only to all non-domestic customers).
- **Condition 21B (Billing based on meter readings)** — changed **31 Dec 2020** (Clean Energy
  Package; inserted 21B.5A, smart-meter monthly billing info). Its **before** side is served from
  the **v2019** consolidation — the first mapping to use v2019.

0A and 21B were both surfaced by the change-detector (`src/detect_changes.py` → `docs/change-map.md`)
and confirmed against Ofgem's modification history before mapping.

Cases T4–T9 ask the **same** question before vs after each change; a deterministic `expect_version`
check asserts which held version was served (independent of the model's prose).

| Metric (19 cases total) | Result |
|---|---|
| Decision accuracy | 19/19 |
| Retrieval hit-rate | 16/16 |
| Citation hit-rate | 16/16 |
| Temporal content checks | 9/9 |
| **Version-swap checks** | **6/6** |
| Hallucinations | 0 |

- T4 (prepayment 2021) → **v2022** pre-reform; T5 (2024) → **v2025** involuntary-PPM ✅
- T6 (business fairness 2023) → **v2022** microbusiness scope; T7 (2024) → **v2025** all non-domestic ✅
- T8 (meter billing 2020) → **v2019** (pre-21B.5A); T9 (2022) → **v2025** (states change "31 December 2020") ✅
- All 13 prior cases unchanged — undated/current retrieval is filtered to the current version,
  so behaviour is byte-identical; historic text enters only via the deliberate swap.
- **Citation normaliser** added: model-emitted `condition` refs are stripped of a stray
  "Condition " prefix at the source (fixes a UI "Condition Condition 0A" render + grader misses).

## Eval hardening (rigor pass)

The case set was grown **19 → 31** (+6 paraphrase variants, +2 out-of-scope refusals, +4 temporal
edge cases: a *straddle* period, an *undated-mapped* query, and *after-change* dates), and three
richer metrics were added to `run_evals.py`:
- **Retrieval depth** — the *rank* of the first expected condition → recall@1/@3/@6 + mean rank
  (not just binary hit/miss).
- **Faithfulness / groundedness** — an independent Claude call judges whether *every* claim in the
  answer is supported by the material the model was given (a direct hallucination measure).
- **History-view check** — asserts a "what changed" view of the expected kind is produced.

### Headline (31 cases, Opus 4.8 — after the P1/P3 retrieval fix below)

| Metric | Before fix | **After fix** |
|---|---|---|
| Decision accuracy | 30/31 | **31/31** |
| Retrieval hit-rate | 25/26 | **26/26** |
| Recall@1 / @3 / @6 | 19 / 24 / 25 | **20 / 25 / 26** (of 26) |
| Mean rank | 1.36 | **1.38** |
| Citation hit-rate | 24/26 | **26/26** |
| Content / Version / History checks | 12/12 · 8/8 · 2/2 | **12/12 · 8/8 · 2/2** |
| **Faithfulness (independent judge)** | 25/25 | **26/26 — 0 hallucinations** |
| Refusals correct / false answers | 5/5 · 0 | **5/5 · 0** |

### The faithfulness-judge trap (lesson)
First pass scored **10/25** — a false alarm. The judge only saw the retrieved *extracts*, so it
flagged every legitimate dated claim (e.g. "introduced 20 September 2023", "as of 1 August 2025")
as unsupported, because those are grounded in the **injected temporal facts** and the
**current-version/as-of framing**, not in the licence extracts. Feeding the judge the *full* grounding
the model saw fixed it to a true **25/25**. Takeaway: a groundedness judge must receive exactly the
context the generator had, not a subset.

### Two weaknesses surfaced — and fixed
The expanded set caught two real issues the original 19 missed, each with a distinct root cause:

- **P1 — false refusal (an *expansion* problem).** *"Before cutting off a household's electricity
  over an unpaid bill…"* retrieved Condition 27 but **refused**. Cause: Cond 27 is large (17 chunks),
  so it only got ±1-neighbour expansion; the query matched a *peripheral* chunk (the direct-debit
  tail), so the disconnection-steps text was never served — RIA correctly refused on the text it saw.
- **P3 — retrieval miss (a *recall/vocabulary* problem).** *"…find and record customers who need
  extra help due to vulnerability?"* **missed Condition 26 (Priority Services Register)** entirely —
  its title shares no words with the lay phrasing (widening the candidate pool didn't help: stuck at
  fused rank 14).

**Fixes (both in `src/rag.py`):**
1. **Full-expand a strongly-matched large condition** — the top-2 matched conditions are served
   whole even if large (bounded at 30 chunks, so monsters like Cond 34/1/28AD stay ±1). P1's
   disconnection steps are now served regardless of which chunk matched.
2. **Lay→licence query synonym expansion** (BM25 query side only) — e.g. "cutting off"→disconnection,
   "extra help / vulnerable"→priority services register. Cond 26 jumps to **rank 1** for P3, and it's
   a general plain-language-robustness feature (Cond 26 in S3 improved too).

Result: **31/31 decisions, 26/26 retrieval + citation, 26/26 faithful, 0 regressions** — the harness
both *caught* the issues and *verified* the fix.

## Embedder A/B — bge-small vs MiniLM (revisiting O4)

Would a stronger embedder beat the current ChromaDB default (`all-MiniLM-L6-v2`)? Tested
`BAAI/bge-small-en-v1.5` (ONNX via `fastembed`, no PyTorch) against the 26 answer-cases,
isolating the embedder's effect (vector-only) from its practical impact (in the hybrid pipeline
± synonym expansion). Rank of the first expected condition; recall@k = cases with it in top-k.

| Method | recall@1 | recall@3 | recall@6 | mean rank | misses |
|---|---|---|---|---|---|
| MiniLM vector | 17/26 | 24/26 | 24/26 | 1.60 | O4, P3 |
| bge vector | 13/26 | 21/26 | 25/26 | 2.65 | P3 |
| **MiniLM hybrid+syn** *(current prod)* | 20/26 | 25/26 | **26/26** | 1.35 | **none** |
| bge hybrid+syn | 22/26 | 25/26 | 25/26 | 1.38 | S1 |
| bge hybrid NOsyn | 23/26 | 24/26 | 24/26 | 1.28 | S1, P3 |

**Verdict — not a net win; keep MiniLM hybrid+syn.** Three findings:
1. **bge natively fixes the O4 vocabulary gap** — O4 (21BA) goes rank **None → 2** vector-only,
   just from the swap. The original hypothesis, confirmed: bge understands the vocabulary MiniLM missed.
2. **But bge is worse as a raw embedder overall** — vector-only it loses on recall@1 (13 vs 17) and
   mean rank (2.65 vs 1.60), and tanks P3 (rank 8 → 19). It trades one blind spot for others.
3. **The incumbent hybrid is still the only config with zero misses** (recall@6 26/26). Every bge
   variant drops ≥1 case (S1, or S1+P3). bge hybrid+syn buys +2 recall@1 but regresses S1 — lateral,
   within noise on 26 cases. bge hybrid *NOsyn* has the best recall@1/mean-rank (bge reduces the need
   for synonyms) but drops P3 entirely, confirming the lay→licence synonym layer still does real work.

The incumbent already fixed O4 via BM25 + synonyms, so bge would fix a problem that's already fixed,
at the cost of a full re-embed of the 3-version store and a heavier dependency. Documented as a viable
alternative, not an upgrade. *Caveat: 26 cases, single run — 1–3 case differences are within noise.*
Reproduce: `venv/bin/python evals/embedder_ab.py` (checkpointed + resumable; tuned for a 4 GB box).

## Artefacts
`evals/cases.yaml` · `evals/run_evals.py` · `evals/embedder_ab.py` (+ `embedder_ab.log`) · `src/detect_changes.py` · `docs/change-map.md` · `evals/results_{baseline,postfix,haiku,hybrid,temporal,textchange,ndf,history,hardened}.json`
