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

## Artefacts
`evals/cases.yaml` · `evals/run_evals.py` · `evals/results_{baseline,postfix,haiku,hybrid}.json`
