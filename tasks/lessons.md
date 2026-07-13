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

## Hybrid retrieval (O4 fix)

- **Hybrid retrieval took three compounding pieces, each measured — not one silver bullet.**
  (1) BM25 + vector fused by RRF; (2) but the verbose query diluted the keyword signal
  (21BA ranked 36th), fixed by **title field-boost ×8** (the condition title is a
  high-signal field); (3) plus **whole-condition expansion for small conditions** so the
  keyword hit actually delivered the chunk with the "12 months" rule. Each step was swept
  or eval-verified before the next. Result: 9/10 → 10/10, zero regressions.

- **RRF sidesteps the score-scale problem.** Vector cosine distance (~0.8) and BM25 scores
  (~15) are incomparable; Reciprocal Rank Fusion combines by *rank position*, so no
  normalisation or weight tuning is needed.

- **Stopword removal isn't free** — it degraded O1 in the sweep. Test corpus-specific
  choices against controls; don't assume a "standard" NLP step helps.

- **Watch O(n²) in throwaway experiments.** A BM25 sweep that called `get_scores` inside
  the sort comparator hung; compute the score array once per query, then sort.

## Phase 5 — Evals

- **Measuring a fix beats assuming it.** The "embed condition titles" fix for O4 *felt*
  obviously right — but measured, it moved 21BA only from absent→rank 18 (still a false
  refusal), so we reverted it. Without the eval we'd have shipped a non-fix and believed
  the problem solved. The evidence (keyword "Backbilling" → exactly 21BA's 4 chunks) then
  pointed cleanly at hybrid retrieval as the real fix.

- **A/B on substance vs format.** Opus 4.8 and Haiku 4.5 scored *identically* on decision
  accuracy (9/10), retrieval (6/7), and hallucinations (0) — retrieval is model-independent.
  The only gap was citation *formatting*: Haiku emits sub-paragraph refs (`27.11`) / prefixes
  (`Condition 0`) where Opus emits the bare condition number. Lesson: a strict grader
  conflates "found the right thing" with "formatted it right" — separate the two, and
  tighten the output schema's field descriptions so weaker models comply.

- **Model capability differs by feature.** Haiku 4.5 400s on `thinking: adaptive` and
  `effort` (Opus/Sonnet-5 features) but supports structured output. Branch the request by
  model rather than assuming one shape fits all.

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

## Post-Phase-6 — embedder A/B, crash-hardening, deploy hygiene

- **The "obvious upgrade" isn't always one — measure it.** Swapping to a stronger embedder
  (`bge-small`) *felt* like a clear win and does natively fix the O4 vocabulary gap (21BA
  None→2 vector-only). But measured over the answer-cases it was **worse as a raw embedder**
  (recall@1 13 vs 17; P3 8→19) and **no config beat MiniLM hybrid+syn**, the only one with
  zero recall@6 misses. Kept MiniLM. Same lesson as the O4 title-embedding non-fix: the
  pipeline (BM25 + synonyms) had already solved the problem the embedder swap targeted.

- **On a 4 GB box, a naive heavy job gets OOM-killed — isolate memory phases + checkpoint.**
  The embedder A/B crashed twice (the session "booted out") loading Chroma + BM25 + the ONNX
  model + all vectors in one process on ~1.8 GB WSL. The fix that made it complete: (1) two
  memory-isolated phases — embed holds ONLY the model + texts, then `del texts` before Chroma/
  BM25 load; (2) small batches + capped ONNX threads; (3) **atomic, resumable checkpointing**
  (tmp-file + `os.replace`) so a crash resumes from the last flush, not from zero. Template:
  `evals/embedder_ab.py`. Also: raise WSL swap via `.wslconfig` (needs `wsl --shutdown` to
  take effect — a Windows-side step, easy to forget).

- **Lost uncommitted work is recoverable from the Claude session transcript.** After the crash
  lost the A/B script (never committed, scratchpad cleaned), it was reconstructed from
  `~/.claude/projects/<proj>/<session>.jsonl` — the Write/Edit tool-use inputs hold the exact
  file contents. Lesson: commit experiment scripts early; if not, the transcript is the backup.

- **Streamlit Community Cloud can half-update on push → reboot after every deploy.** A live
  crash looked like a code bug but the repo was fully consistent and worked end-to-end locally.
  Cause: the running instance served a new `main.py` against a **stale module** missing a
  newly-added function → AttributeError *at the call site with no deeper frame* (the signature
  of "module has no attribute"). Fix: reboot the app (Manage app → ⋮ → Reboot). Prevention:
  reboot after any deploy, and **guard supplementary UI** so a half-update degrades (skip the
  panel) instead of crashing the whole answer.

- **Verify state against disk, not against a claim (either direction).** Twice this stretch a
  stated project state was wrong — once too pessimistic ("fresh start at Phase 2" when the repo
  was fully built), once corrected by me too hastily ("no embedder work existed" when the
  transcript proved it did). Git log, file listings, and the transcript are the ground truth;
  check them before asserting or agreeing.

## Phase 7 — broad-query completeness (query planning) + licensing

- **Broad-query completeness is a recall problem, and recall is an accuracy requirement.** The
  system was tuned for precision on narrow questions, so "what are ALL our duties around X?"
  surfaced ~2 of the relevant conditions (baseline 47% Core recall on the anchor set). A
  corpus-aware planner (wide-net retrieve → let the model pick relevant conditions from their
  titles → one focused sub-query per obligation area → union) lifted retrieval recall to 100%.

- **Corpus-aware planning beats blind decomposition, and targeted sub-queries reach what a broad
  query structurally can't.** Killer evidence: "billing obligations" cannot retrieve Cond 21BA
  even at depth 40, but a narrow "back-billing" sub-query surfaces it at rank 1. Grounding the
  plan in the corpus's own vocabulary avoids the O4-style vocabulary gap.

- **Measure retrieval recall AND answer recall separately.** Retrieval union hit 100% Core, but
  the synthesized ANSWER cited 82% — synthesis is selective. Retrieval recall is a ceiling, not
  the delivered number; grade the citations, not just the fetch.

- **Decomposition trades precision for recall — guard the refusal discipline explicitly.** The
  broad pipeline over-answered an out-of-scope question (Guaranteed Standards) by latching onto a
  tangential condition (14A) — a false answer the narrow system correctly refused. Fix was a
  SCOPE DISCIPLINE instruction: answer only what the extracts actually address; refuse when the
  question's CORE subject isn't in them, even if a related condition surfaced.

- **Backward-compat derivation lets a big output-schema change land with zero regressions.** The
  new grouped-by-obligation schema derives the old `answer` (markdown) + `citations` fields, so
  the UI, the 31-case eval harness, and the temporal-history panel kept working untouched —
  regression gate stayed green (31/31) without touching consumers.

- **A pre-existing cap can silently fight a new feature.** `views_for(limit=2)` was a sensible
  anti-clutter guard when answers cited ~1 mapped condition; broad multi-condition answers then
  silently dropped the 3rd temporal panel. When a feature changes cardinality assumptions, hunt
  for constants/limits set under the old assumption.

- **Absence-of-signal can imply a false claim; make coverage explicit.** Showing a version-history
  panel for one cited condition but not others could be read as "those never changed" when the
  truth is "not mapped yet." A generated coverage line ("mapped so far for 0A, 4D, 21B, 25E, 28")
  turns the ambiguity into an honest, self-updating statement.

- **Licence to intent, not by default: MIT would give away the thing you want to sell.** For a
  public portfolio repo that may be commercialised later, MIT grants everyone the right to use,
  modify, and SELL the code — the opposite of the goal. "All Rights Reserved" (source-visible,
  no reuse rights) keeps portfolio visibility while reserving commercial rights. GitHub won't
  badge a custom licence (licenseInfo=null) but the LICENSE file is still effective.

- **Security-through-obscurity isn't security.** Removing the README to "hide what it does"
  protects nothing — the code IS the disclosure. Real levers: the LICENSE (legal deterrent) and
  repo privacy (removes the code from view). Keep the README; its portfolio value dwarfs its
  negligible effect on copying.

- **A new capability can outdate a gold standard — inspect the output before calling it a
  regression.** The compound-scope fix flipped case D2 from refuse→answer, showing as a 30/31
  "regression". But D2 is near-identical to A4 (which we WANTED answered-with-caveat), and the
  actual output was a good, honest compound answer (14A switching timescale + a note that
  Guaranteed Standards compensation is out of scope). The eval gold ("refuse") predated the
  answer+caveat capability. Fix was to update D2's gold (with sign-off) — NOT eval-gaming, because
  the new behaviour is genuinely better and the judgement was made by reading the answer, not by
  chasing a green number. Distinguish "gold outdated by a real improvement" from "system got worse"
  every time a fix moves a previously-passing case.

- **Partial/compound scope needs its own path, distinct from pure out-of-scope.** Pure out-of-scope
  → refuse. Compound (some parts covered, some not) → answer the covered parts AND name the
  uncovered part (an `out_of_scope_note`). A single "refuse if core subject is out of scope" rule
  over-refuses compound questions; a single "answer what you can" rule over-answers them. Both are
  needed, and the diagnostic surfaced exactly this gap.

- **Measure whether you actually need the expensive model — sometimes the cheap one ties.** The
  planner (decompose the question into sub-queries) runs on Haiku; a quick A/B vs Opus showed
  IDENTICAL anchor Core recall (16/17 both). So the plan step moved to a ~10x-cheaper model with
  zero quality loss, cutting one of the two per-query LLM calls on the live paid demo. Mirror image
  of the embedder A/B (where the "upgrade" lost): don't assume the pricier/bigger option is needed —
  A/B it on the metric that matters. Put the expensive model only where it earns its keep (here,
  grounded synthesis stays on Opus).

- **Separate the two LLM roles so each can use the right model.** Planning and synthesis were
  initially coupled to one model param; decoupling them (`PLANNER_MODEL` vs the synthesis model)
  was what made the Haiku cost-cut a one-line change and keeps a clean seam for future tuning
  (e.g. a cheaper synthesis model for narrow queries later).

## Session 2026-07-13 — DEPTH pass (broad-answer recall) lessons

- **Diagnose before you fix; the obvious hypothesis was half-wrong.** I assumed broad-answer recall
  loss was one thing (synthesis over-merging conditions). Classifying every dropped Core condition as
  *in-context-but-dropped* (synthesis) vs *missing-from-context* (retrieval) showed TWO separate
  problems of roughly equal size. Fixing only the assumed one would have left half the gap. The cheap
  classifier harness (planner + local retrieval, no Opus) paid for itself immediately.

- **The recorded baseline was the lucky high end.** The prior note said "82% answer-level recall";
  a 3-run variance check showed 71/76/82 → true mean ~76%. Single-run eval numbers on a
  non-deterministic pipeline are unreliable — always take a small variance sample before setting a
  target, or you measure your "fix" against an inflated bar.

- **Prompt-tuning a retrieval/coverage problem is fighting the wrong battle.** To reach a stubborn
  condition (21BA back-billing, 21A annual statement) I first strengthened the planner PROMPT. It
  netted zero on aggregate AND destabilised previously-solid anchors (forcing "add EACH specific
  obligation" crowded the sub-query budget → round-robin squeezed out a good condition). A local
  rank probe showed the real cause: the target only ranks top-k under an EXACT short term, and the
  LLM dilutes it ("annual statement" ranks #3, "annual statement of consumption domestic" ranks
  None — one extra word kills it). LLMs can't reliably thread that needle. A small DETERMINISTIC
  safety net (inject proven-phrasing sub-queries verbatim, additive so planner coverage isn't
  displaced) was reliable AND non-disruptive. Reach for determinism when the fix is "use exactly
  this string", not "reason better".

- **An additive retrieval booster can still cause REFUSALS.** The safety net only ADDS sub-queries,
  yet a loose trigger caused 2 false refusals: billing hints fired on a disconnection question
  ("unpaid bill") and a Guaranteed-Standards question (billing conditions among its wide-net
  candidates), and the injected off-topic chunks DISPLACED the real extract from the budget-capped
  union → synthesis had nothing to answer from → refused. Lesson: a budget-capped union means adding
  the wrong thing removes the right thing. Gate any injected retrieval NARROWLY (match the QUESTION
  only, SPECIFIC terms not generic), and ALWAYS run the full refusal suite — the regression caught
  it before ship. Under-firing is safe (degrades to normal planner); over-firing breaks unrelated
  questions.

- **A condition's TITLE can lie; verify anchors against the BODY.** The last recall "residual"
  (21A reached context but was never cited) was not a bug — 21A's title "annual statement" sounds
  like domestic billing, but its TEXT is the CRC (Carbon Reduction Commitment) Energy Efficiency
  Scheme statement to NON-domestic Participants. Synthesis was CORRECT to exclude it from a domestic
  billing question. The GOLD was wrong (21A shouldn't have been in BQ2's Core), even though the
  anchor set was "verified vs Ofgem". Fix the gold when the evidence says it's off — never train the
  system to cite an out-of-scope condition to satisfy a wrong target (same discipline as the D2
  gold-update). A system correctly refusing/excluding is right behaviour, not a miss.

- **Concurrency amplifies API flakiness on structured output.** Running two structured-output eval
  jobs at once hit transient 503 "grammar compilation unavailable" + a truncated-JSON decode error.
  Re-running SOLO succeeded every time — not code bugs, just load. When the API is unstable, serialise
  the structured-output jobs. (Latent robustness note: synthesis has no retry/repair on a malformed
  JSON response — worth hardening if it recurs.)

- **Second title-vs-body anchor error (BQ3 Cond 45) — the pattern generalises.** After 21A, a
  body-check of BQ3's remaining "3/4" found the dropped condition (45 "Smart Metering Consumer
  Engagement") was ALSO a soft anchor: it's about funding a central engagement body (Smart Energy
  GB), not an install duty, AND it ceased 30 Jun 2021. Synthesis was right to drop it for an
  operational install question. Re-scoring on corrected anchors lifted the measured recall ~92% ->
  ~98% WITHOUT touching the system — the "misses" were mostly eval error. Takeaways: (1) when a
  small hand-built gold set has a systematic-looking gap, suspect the gold before the system;
  (2) re-scoring recorded outputs against a corrected gold needs NO re-run (the model's citations
  are unchanged — only their classification is); (3) don't chase 100% on a 5-case set — the honest
  move for confidence is a bigger, body-verified anchor set, not prompt-squeezing the last point.
