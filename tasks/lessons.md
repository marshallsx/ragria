# Lessons

Running log of what we learned building RAGRIA — the non-obvious stuff worth remembering.

## Phase 2 — Ingestion

- **`pdfplumber` is too slow for full-document extraction.** It does per-page layout
  analysis; scanning all 611 pages timed out (>2 min) and froze the terminal. `pypdf`
  extracts the same plain text in ~20s. Use `pypdf` when you only need text; reserve
  `pdfplumber` for when you actually need tables/layout.

- **Run heavy jobs in the background, and cache the slow step.** Extract-to-cache
  (`data/interim/slc_pages.jsonl`) once, then every chunking iteration reads the cache
  instantly. Background execution keeps the terminal free and un-freezable.

- **Structure-aware chunking needs an explicit completeness check.** Splitting on
  `Condition N` headings is only as good as the heading regex. Our first regex handled
  single-letter suffixes (`21A`) but silently missed **two-letter** ones
  (`19AA`, `21BA "Backbilling"`, `28AA`, `28AD` — the price-cap conditions). Their text
  got merged into the previous condition with the wrong citation. Always diff "headings
  the strict regex matched" against "all heading-like lines" to catch silent merges.

- **The end-to-end smoke query is what exposed the bug.** Unit-level checks (chunk count,
  spot-checks) looked fine; it was querying *"back-billing"* and seeing it attributed to
  Condition 21B (not 21BA) that revealed the merge. Always include a real query in the
  verify gate, not just structural stats.

- **Tightening a regex can silently drop data.** Requiring the title to start with `[A-Z]`
  fixed the suffix bug but dropped 4 conditions whose titles start with `(` (e.g.
  `25A. (Not used.)`). Net count stayed 107, masking the change. Watch totals when you
  change a matcher — a coincidental same-count can hide a swap.

## Phase 3 — Retrieval + grounded generation

- **Distance thresholds are a poor refusal mechanism with a weak embedder.** In-scope
  questions scored best-distance 0.71–0.95; a clearly out-of-scope question scored 1.07 —
  the bands nearly touch, so any single cutoff either wrongly refuses good questions or
  lets bad ones through. The robust design is **LLM-judged refusal** (give the model the
  extracts + strict "answer only from these" instructions, let it decide), with the
  distance number kept only as a lenient backstop to skip API calls on egregious junk.

- **Fixing the ingestion bug visibly improved retrieval.** Once 21BA "Backbilling" was
  parsed as its own condition (Phase 2 fix), it went from rank 3 (buried in 21B) to
  **rank 1** for the back-billing query. Retrieval quality is downstream of chunking
  correctness — a citation/parsing bug is also a retrieval bug.

- **The weak embedder causes false refusals via vocabulary gaps — the #1 retrieval risk.**
  "Can a supplier back-bill more than 12 months ago?" retrieves Condition 21BA at rank 1
  and answers perfectly; the near-synonym "What is the **maximum back-billing period**?"
  doesn't surface 21BA even in the **top 15**, so the system refuses a question the corpus
  answers. Raising k does not help (it's a semantic-match failure, not a threshold one).
  Candidate fixes, cheapest first: (1) **embed the condition title with the chunk text**
  so "Backbilling" is in the vector; (2) **hybrid BM25 + vector** retrieval so the keyword
  matches; (3) a stronger embedder (reintroduces the model dependency v0 avoided). Recorded
  as O4 in `docs/query-taxonomy.md`; quantify + fix in Phase 5.

- **Small chunks clip multi-part conditions — fix with neighbour expansion.** The
  back-billing answer honestly flagged that 21BA's exceptions were truncated: 21BA is 4
  chunks and only chunk 0 (rule + start of exceptions) was retrieved; chunk 1 (rest of
  the exceptions) wasn't in the top-6. Fix = **small-to-big retrieval**: after ranking on
  small windows, pull each hit's adjacent chunks (chunk_index ±1) from the same condition
  and feed Claude the completed, in-order text. Bounded to ±1 so giant conditions (e.g.
  Cond 34 = 131 chunks) can't flood context. The model surfacing the limitation itself is
  the signal that led to the fix — grounded honesty is a debugging aid, not just a safety
  feature.

- **Adaptive thinking + structured output on Opus 4.8:** use `thinking={"type":"adaptive"}`
  (no `budget_tokens` on 4.7/4.8) and `output_config={"format": {json_schema}}`. With
  thinking on, the first content block is a thinking block — extract the *text* block
  (`next(b for b in resp.content if b.type=="text")`), not `content[0]`.

- **The Max subscription does not cover API usage.** claude.ai / Claude Code run on the
  subscription; this app calls the Anthropic API with the `sk-ant-` key and is billed
  separately (pay-as-you-go). At PoC scale it's single-digit dollars regardless of model.

- **ChromaDB default embedder = `all-MiniLM-L6-v2`, 256-token cap, CPU/onnxruntime.**
  One-time ~80MB model download on first use. Embedding 1133 chunks takes ~6 min on CPU
  (one-off; queries are fast). The 256-token limit drives chunk size (~175 words). It's
  only moderately discriminating on dense legal text — a retrieval-quality item to
  measure in the eval phase.
