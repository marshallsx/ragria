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

## Artefacts
`evals/cases.yaml` · `evals/run_evals.py` · `src/detect_changes.py` · `docs/change-map.md` · `evals/results_{baseline,postfix,haiku,hybrid,temporal,textchange,ndf}.json`
