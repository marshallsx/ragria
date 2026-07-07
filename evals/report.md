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

## Headline result (baseline — Opus 4.8)

| Metric | Result |
|---|---|
| Decision accuracy | **9/10** |
| Retrieval hit-rate (answer cases) | 6/7 |
| Citation hit-rate (answer cases) | 6/7 |
| False answers (hallucinations) | **0** |
| Correct refusals | D1, D2, S4 ✅ |
| False refusals | **O4** |

**The system is grounded and disciplined:** every out-of-scope question (Ombudsman
deadline, Guaranteed Standards, gas-boiler safety) is correctly refused, and it never
invented an answer. The single failure is **O4**, a false refusal.

---

## The one failure: O4 (false refusal)

*"What is the maximum back-billing period for domestic customers?"* is refused, even
though the corpus answers it (Condition 21BA = 12 months) and answers the near-synonym
*"can a supplier back-bill more than 12 months ago?"* (S1) at rank 1. Cause: a
**vocabulary gap** in the default embedder (`all-MiniLM-L6-v2`) — the query says
"maximum back-billing period"; the 21BA chunk says "Backbilling / 12 months preceding".

### Fix attempted and measured → reverted
**Hypothesis:** embed each chunk *with its condition title* so "Backbilling" is in the
vector. **Measured:** 21BA moved from *absent in top-15* → **rank 18** — still far outside
the top-6, so O4 stayed a false refusal (post-fix score unchanged at 9/10). The change
also polluted the retrieved context with a redundant condition prefix on every chunk, so
it was **reverted**.

### Recommended fix (evidenced): hybrid retrieval
The keyword "Backbilling" appears in **exactly the 4 chunks of Condition 21BA and nowhere
else** — a keyword match pinpoints it where semantics fail. A **hybrid BM25 + vector**
retriever is the real fix. It's a larger change (keyword index, score fusion,
case/hyphen normalisation) and is **deferred beyond lightweight v0**.

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

1. **O4 vocabulary-gap false refusal** — top retrieval risk. Fix: hybrid keyword+vector.
2. **Citation field formatting** — weaker models put sub-paragraph refs in the `condition`
   field. Cheap fix: tighten the schema description to "bare condition number, e.g. `21BA`".
3. **Grader is strict on citation format** — it does exact-match on the condition string;
   a normalising matcher (strip sub-paragraph suffix / "Condition " prefix) would measure
   *grounding* more fairly, separately from *format*.

## Artefacts
`evals/cases.yaml` · `evals/run_evals.py` · `evals/results_{baseline,postfix,haiku}.json`
