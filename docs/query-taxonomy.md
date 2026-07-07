# Query Taxonomy (eval seed)

Categorised questions used to exercise and evaluate RIA. This seeds the Phase 5
eval harness: each case has an **expected outcome** and the **observed behaviour**
at the time of writing (2026-07-07, Opus 4.8, k=6, neighbour expansion on).

Legend — Expected: `answer` (should answer from the electricity supply SLCs) ·
`refuse` (correctly out of the electricity supply SLC corpus).

---

## Obligations

| # | Question | Expected | Observed | Notes |
|---|----------|----------|----------|-------|
| O1 | What must we do before disconnecting a domestic customer for debt? | answer | ✅ answered — **C27** | Good. |
| O2 | What are our Priority Services Register obligations for identifying and recording vulnerable customers? | answer | ✅ answered — **C26, C28** | Strong match (dist 0.71). PSR = Condition 26. |
| O3 | What must we tell a customer when a fixed-term tariff ends, and how far ahead? | answer | ✅ answered — **C22C, C31I** | Good. |
| O4 | What is the maximum back-billing period for domestic customers? | answer | ❌ **REFUSED (false negative)** | **Retrieval bug.** Corpus answers this (C21BA = 12 months) and answers the phrasing *"can a supplier back-bill more than 12 months ago?"* at rank 1 — but this phrasing doesn't surface 21BA even in the top 15. Embedder vocabulary gap. |

## Deadlines / Timelines

| # | Question | Expected | Observed | Notes |
|---|----------|----------|----------|-------|
| D1 | What is the deadline to resolve a complaint before it can escalate to the Energy Ombudsman? | refuse | ✅ refused | Correct — the 8-week rule lives in the *Consumer Complaints Handling Standards Regulations 2008*, not the supply SLCs. |
| D2 | What are the Guaranteed Standards switching timescales, and what compensation applies if missed? | refuse | ✅ refused | Correct — Guaranteed Standards of Performance sit in separate regulations, not the supply SLCs. |

## Earlier smoke/verify questions (Phase 3)

| # | Question | Expected | Observed |
|---|----------|----------|----------|
| S1 | Can a supplier back-bill a domestic customer for consumption more than 12 months ago? | answer | ✅ C21BA |
| S2 | Can a supplier block a customer from switching to another supplier? | answer | ✅ C14, C14A |
| S3 | What protections apply to customers in vulnerable situations? | answer | ✅ C0, C31G |
| S4 | What safety certifications are required to install a domestic gas boiler? | refuse | ✅ refused |

---

## Findings to carry into Phase 5

1. **False refusals from embedder vocabulary gaps (O4) are the top retrieval risk.**
   The content is present and correctly cited under one phrasing but invisible under a
   near-synonymous one. Candidate fixes (cheapest first):
   - **Embed the condition title with the chunk text** (e.g. prefix "Condition 21BA —
     Backbilling: …") so title vocabulary is in the vector. Small ingestion change; re-embed.
   - **Hybrid retrieval** (BM25 keyword + vector) — keyword "back-billing" would match the
     "Backbilling" chunk directly, bridging the vocabulary gap.
   - **Stronger embedder** (real fix, but reintroduces a model dependency we deliberately avoided in v0).
2. **Correct out-of-corpus refusals (D1, D2) are the scope boundary working.** Answering
   them would require broadening the corpus beyond the electricity *supply* SLCs
   (complaints-handling regs, standards-of-performance regs) — a deliberate later decision,
   not a v0 gap.
3. Phase 5 should report **pass/fail per case** against the Expected column and separate
   *false refusals* (retrieval weakness) from *correct refusals* (scope boundary).
