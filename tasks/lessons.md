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

- **ChromaDB default embedder = `all-MiniLM-L6-v2`, 256-token cap, CPU/onnxruntime.**
  One-time ~80MB model download on first use. Embedding 1133 chunks takes ~6 min on CPU
  (one-off; queries are fast). The 256-token limit drives chunk size (~175 words). It's
  only moderately discriminating on dense legal text — a retrieval-quality item to
  measure in the eval phase.
