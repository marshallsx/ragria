# RIA — How it works (design & retrieval rules)

A precise walk-through of the Regulatory Intelligence Assistant: how it ingests the licence,
**how conditions are identified**, **how retrieval works**, and how it grounds, dates, and
answers. Written to be read top-to-bottom; the two sections you asked about most — *Identifying
conditions* and *Retrieval* — are §2 and §4.

---

## 1. Pipeline at a glance

```
PDF consolidations (v2019 / v2022 / v2025)
   │  extract_pages.py      → per-version page cache (JSONL)
   │  chunk.py              → condition-tagged chunks (JSONL)   ← §2 identification
   │  embed.py              → ChromaDB vector store (+ BM25 built in memory at query time)
   ▼
QUESTION (+ optional "as of" date)
   │  out-of-scope backstop (cheap, no API)                     ← §5
   │  planner (Haiku): decompose → sub-queries                  ← §3
   │  per sub-query: hybrid retrieve (vector + BM25 + RRF)      ← §4
   │  union + dedupe (round-robin, budget 40)                   ← §4
   │  version resolution per condition (as-of date)             ← §6
   │  whole-condition / neighbour expansion                     ← §4
   ▼
SYNTHESIS (Opus): grounded, grouped-by-obligation answer + citations + scope note  ← §7
```

Two models: **Haiku** plans (cheap), **Opus** synthesizes (grounded generation). Embeddings are
ChromaDB's built-in `all-MiniLM-L6-v2` (no PyTorch).

---

## 2. Identifying conditions (ingestion) — `src/chunk.py`

The **Condition** is the unit of everything: retrieval, citation, temporal mapping. Conditions are
identified **once, at ingestion**, by a structure-aware parser — not by the LLM, and not at query
time. Each chunk is permanently tagged with the condition it belongs to.

**The parser** walks the licence body line by line and detects a condition *heading* with one regex:

```python
COND = re.compile(r"^Condition\s+(\d+[A-Z]{0,3}(?:\.[A-Z])?)[.:]\s+(.+)")
```

What this matches, and why each part matters:
- **`^Condition\s+`** — the line must *start* with the capitalised word "Condition". This excludes
  inline cross-references (which read "…under condition 27…", lowercase) and mid-sentence mentions.
- **`\d+[A-Z]{0,3}`** — a number plus up to **three** capital letters. This is what lets it capture
  multi-letter conditions like **21BA, 19AA, 28AA, 28AD** (an earlier version allowed only one
  letter and silently merged these into their neighbours — a real bug caught by an end-to-end query,
  now fixed by `{0,3}`).
- **`(?:\.[A-Z])?`** — an optional dotted form like **12.A**.
- **`[.:]\s+(.+)`** — a "." or ":" **followed by a space**, then the title. The required space is
  what distinguishes a *heading* ("Condition 28. Prepayment Meters") from a *sub-paragraph
  reference* ("28.4", no space) — so the parser never mistakes a clause reference for a new condition.

Everything between one heading and the next is grouped as that condition's body. Section headings
(`SECTION A`, `SECTION B…`) are tracked separately and attached as metadata. Repeated page
headers/footers and bare page numbers are filtered as boilerplate.

**Chunking.** Each condition's body is split into overlapping word-windows — **175 words with 25
overlap** — sized to stay under the embedder's ~256-token cap. Small conditions become one chunk;
large ones become several, in reading order. "Not used" conditions keep a stub chunk so they remain
queryable.

**Metadata on every chunk** (this is what makes citation and grouping possible without re-parsing):
`condition`, `condition_title`, `section`, `page_start/​end`, `chunk_index`, `n_words`,
`version_label`, `version_date`, `source_authority`, `url`, `source`, `doc_title`.

**Chunk IDs are namespaced by version:** `"{version}__cond{n}_{idx}"` (e.g.
`2025-08-01__cond28_3`). So the *same* condition in different consolidations never collides in the
store — essential for the temporal feature (§6).

---

## 3. Query planning (broad-query completeness) — `src/planner.py`

The system is tuned for precision, which under-answers *broad* questions ("what are all our duties
to vulnerable customers?"). The planner fixes that by turning one question into several focused
searches. It is **corpus-aware**, not blind:

1. **Wide-net retrieve** — a deliberately broad pull (vector top-40 ∪ BM25 top-40) to see which
   conditions *actually exist* in the corpus that relate to the question (≤ 25 candidates).
2. **Plan** — Haiku is shown the question + those candidate condition **titles**, and returns:
   - `is_broad` (specific vs broad), and
   - a focused **sub-query per obligation area**, phrased in the licence's own vocabulary. For a
     *specific* question it returns just one sub-query (≈ the original). It may also add a sub-query
     for a well-known specific obligation even if absent from the candidates (e.g. "back-billing"),
     because a targeted sub-query reaches conditions a broad phrasing structurally misses.
3. The **original question is always kept as the first sub-query**, so planning can only *add*
   coverage, never regress below single-query behaviour. Capped at **6 sub-queries total**.

Why corpus-aware: a blind decomposition would invent facets and hit the same vocabulary gap the
retriever has; grounding the plan in real condition titles avoids that.

---

## 4. Retrieval — `src/rag.py` (the core rules)

Retrieval runs **per sub-query** and the results are unioned. Each sub-query goes through the same
**hybrid** pipeline:

### 4a. Two retrievers, fused
- **Vector** (`vector_retrieve`): ChromaDB semantic search, top `CAND_N = 10`, **filtered to the
  current version** (`where version_label == CURRENT`). Historic text never enters here — it enters
  only via the deliberate temporal swap (§6).
- **BM25 keyword** (`bm25_retrieve`): a pure-Python BM25 index built in memory over the current
  version's chunks. Two rules make it strong on legal text:
  - **Title field-boost ×8** — each chunk's BM25 document is `(condition_title · 8) + text`, so a
    query that names a condition ("back-billing" → title "Backbilling") ranks it at the top.
  - **Lay→licence synonym expansion** (`expand_query`) — the *query* is expanded with licence-term
    aliases (e.g. "cutting off" → disconnection; "extra help / vulnerable" → Priority Services
    Register). This closes the gap between how people ask and how the licence is worded.
- **Fusion** (`rrf`): the two ranked lists are combined by **Reciprocal Rank Fusion** (constant
  `RRF_K = 60`) → top `TOP_K = 6` per sub-query. A strong keyword hit is not blocked by a weak
  vector score, and vice-versa — that's the whole point of hybrid.

### 4b. Union across sub-queries
Each sub-query yields its ranked chunks; they're merged by **round-robin interleave**: every
sub-query contributes its rank-1 chunk before any contributes its rank-2, deduped by chunk id, up to
a **budget of 40 chunks**. Interleaving guarantees the budget can't be exhausted by one obligation
area before the others are represented — this is what protects *completeness*.

### 4c. Small-to-big expansion (`expand_hits`)
Retrieval ranks on small windows, but the answer needs whole rules. After the union, for each
surfaced condition:
- a **small** current condition (**≤ `EXPAND_FULL_CAP = 8` chunks**) is pulled **whole**;
- a **strongly-matched** large condition (in the top `LARGE_TOP_N = 2`, and ≤ `LARGE_MAX_CHUNKS =
  30`) is also pulled **whole**, so a big but clearly-relevant condition arrives complete;
- any other large condition contributes only its matched chunk **± 1 neighbour** (bounded, so a
  131-chunk monster can't flood the context).

Crucially, **expansion never introduces a *new* condition** — it only fills in chunks of conditions
already surfaced. So *the set of conditions in an answer is fixed by the fused retrieval*, and
expansion just makes each one complete.

### Which conditions "surface"
The conditions an answer can cite = the distinct `condition` metadata values among the retrieved
(and expanded) chunks. The LLM then cites, from the labelled extracts, the specific conditions it
relied on (with a small sanitiser stripping a stray "Condition " prefix). So: **the parser defines
conditions (§2), retrieval selects which ones surface (§4), the LLM identifies which it actually
used (§7).**

---

## 5. Refusal & scope discipline

Two layers, cheap-first:
1. **Out-of-scope backstop (no API).** Before any planning/generation, the original query's best
   *vector* distance is checked against `DISTANCE_FLOOR = 1.6`. Obviously off-topic questions (or
   zero hits) are refused immediately, saving the API spend.
2. **Grounded judgement + scope discipline (in synthesis).** In-scope questions go to Opus, which
   answers **only** from the extracts and applies scope rules:
   - **Pure out-of-scope** (the question's core subject — e.g. Guaranteed Standards compensation,
     the Ombudsman complaint process, gas, a numeric price-cap level — isn't in the extracts) →
     **refuse**, even if a tangential condition surfaced.
   - **Compound** (some parts covered, some not) → **answer the covered parts** and set an
     `out_of_scope_note` naming the uncovered part. A tangential in-scope obligation must not stand
     in for the out-of-scope part.

---

## 6. Temporal / version resolution — `src/temporal.py`

RIA holds three dated consolidations (v2019 / v2022 / v2025); "current" is derived as the latest.
An `as of` date (default = today) selects which version's text applies **per condition**:

- **`version_for(condition, as_of)`** returns the version label whose text was in force then:
  - a condition we've **mapped** and whose text changed (0A, 21B, 28) → the held version for that
    date's segment;
  - a **mapped introduced** condition (25E, 4D) → exists / did-not-exist boundary;
  - anything **unmapped** → the current version (and, for a *past* date, a caveat that the historic
    position isn't confirmed);
  - a date **before our earliest held text** → refuse/caveat.
- Retrieval is version-scoped to *current* (§4a); for a mapped condition on a past date,
  `expand_hits` **swaps** that condition's chunks to the resolved historic version and serves it
  whole. The answer states which consolidation date it relied on.
- Validity is **per-condition and contiguous** — a mapped condition is in force for its whole life;
  the only question is *which text* applied on date X. We only map conditions whose change history
  we can make gap-free from the versions we hold.

The UI shows a version-history panel for each **mapped** cited condition, plus a coverage line
naming exactly which conditions are mapped (so absence of a panel isn't read as "never changed").

---

## 7. Generation (grounded answer) — synthesis in `src/planner.py`

Opus receives: the as-of framing, authoritative **temporal facts**, and the labelled extracts (one
block per condition, headed with its number, title, consolidation date, section, pages). It returns
structured output:
- **`obligations[]`** — each a distinct duty: a short label, a grounded detail drawn *only* from the
  extracts, and citation(s) to the condition(s) it came from;
- **`reason`** (if refused), **`exhaustiveness_note`** ("reflects the retrieved sections; may not be
  exhaustive"), **`out_of_scope_note`** (§5).

The grouped output also derives backward-compatible `answer` (markdown) and a deduped `citations`
list, so the UI, evals, and temporal panels consume one consistent shape. **Faithfulness is
measured**: an independent LLM judge checks every answer is supported by its extracts (last run:
27/27, zero hallucinations).

---

## 8. Models & key constants

| Setting | Value | Where |
|---|---|---|
| Embedder | `all-MiniLM-L6-v2` (ChromaDB default, ~256-token cap) | `embed.py` |
| Planner model | Haiku 4.5 | `planner.PLANNER_MODEL` |
| Synthesis model | Opus 4.8 | `rag.MODEL` |
| Chunk size / overlap | 175 / 25 words | `chunk.py` |
| Vector+BM25 candidates (`CAND_N`) | 10 each | `rag.py` |
| Fused top-k (`TOP_K`) | 6 | `rag.py` |
| RRF constant | 60 | `rag.py` |
| Title field boost | ×8 | `rag.py` |
| Whole-condition cap (`EXPAND_FULL_CAP`) | ≤ 8 chunks | `rag.py` |
| Strong-match full expand (`LARGE_TOP_N` / `LARGE_MAX_CHUNKS`) | top 2 / ≤ 30 | `rag.py` |
| Out-of-scope distance floor | 1.6 | `rag.py` |
| Planner wide-net / candidates | 40 / ≤ 25 | `planner.py` |
| Sub-queries cap | 6 (incl. original) | `planner.py` |
| Per-sub-query k / union budget | 6 / 40 | `planner.py` |

---

*Scope: Ofgem **electricity supply** Standard Licence Conditions only, public consolidations.
Informational, not legal advice.*
