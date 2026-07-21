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

## Session 2026-07-13 (cont.) — expanding the verified anchor set

- **Body-verify gold with tooling + parallel subagents — not by hand, not by title.** Building the
  20-query anchor set, the reliable method was: (1) a full-BODY trap-scan script
  (`scratchpad/anchor_verify.py`) that flags "cease to apply"/"Not used"/past-date (spent),
  Non-Domestic/Micro-Business/CRC (wrong customer type), and reporting-to-Authority-only, over the
  WHOLE condition body (the 45 "ceased 2021" clause was buried mid-condition, not in the title or
  opening); (2) three parallel subagents classifying Core/Borderline/Reject from that evidence with
  a shared rubric. It overturned two of my own hand-picks on body evidence (cond 35 is Green Deal
  not FIT; cond 59 is alternative-fuel not SEG) and rejected a whole cluster of spent conditions
  (28A, 28AA, 24A, 22B, 32A, 45). Title-level or by-memory gold would have baked those errors into
  the regression baseline.

- **A bigger, honest eval set LOWERS the headline number — and that's the win.** ~98% on 5 curated
  anchors became ~90% on 20 diverse ones. That drop is NOT a regression; it's removing measurement
  bias — the tidy set was over-sampling easy queries. The 20-set immediately surfaced a real gap
  (BQ8 tariffs 1/3: 22A/25 unreached, same shape as the old 21A/21BA billing gap) that the 5-set
  structurally couldn't show. Optimise for a TRUER number, not a prettier one; when a metric looks
  great, suspect the sample before trusting the score.

- **The consolidation carries DEAD conditions.** Six ceased/spent conditions surfaced during anchor
  work (28A, 28AA, 24A, 22B, 32A, 45). Eval gold must exclude them — but note the APP still retrieves
  them (they're embedded chunks). Open question for a future session: can the live pipeline ever
  present a CEASED condition as a current obligation? Worth a targeted check (not yet done).

- **Third title-vs-body anchor fix (BQ15 19A/19C) + two flickers exposed.** Diagnosing the last
  three 20-set "residuals": BQ9 (3/3 over 3 runs) and BQ10 (4/4 over 3 runs) were pure SINGLE-PASS
  FLICKER — yesterday's 2/3 and 3/4 came from the one full pass we managed before an API 503 aborted
  pass 2. Building a fix for either would have solved a non-problem. Only BQ15 had real signal, and
  even that was mostly gold: 19A (body = publish a Consolidated Segmental Statement — financial
  REPORTING, not resilience) and 19C (customer supply CONTINUITY plan on exit — BQ9's area) are soft
  members; the canonical resilience/fit-and-proper package 4A/4B/4C is cited reliably. Demoted 19A/19C
  to Borderline (synthesis was right to drop 19A). PATTERN NOW CLEAR: when a hand-built gold shows a
  persistent gap, the FIRST move is variance-check (3 runs) + body-check the dropped condition — most
  "gaps" are flicker or gold error, not system defects. Only genuine, stable, in-scope misses
  (21BA, 22A/31I) warrant a code fix.

## Session 2026-07-14 (cont.) — a real crash bug hiding behind "API flakiness"

- **Synthesis JSON truncation crashed long broad answers — and I'd mis-attributed it to the API.**
  The final 3-pass 20-anchor measurement kept dying at BQ6 (prepayment, ~11 obligations). Root cause
  was NOT a 503: `synthesize()` used max_tokens=4096, and with adaptive thinking the THINKING tokens
  share that budget — so a long grouped-JSON answer stopped mid-string (stop_reason 'max_tokens'),
  `json.loads` raised JSONDecodeError, and the WHOLE answer crashed. This is a live bug (a broad
  prepayment question would crash the deployed app, like the earlier Streamlit incident). Several of
  yesterday's "API flakiness" JSONDecodeErrors were almost certainly THIS, not load — I wrongly waved
  them off. Fix: max_tokens 4096->8192, retry once at 16384 on truncation/malformed parse, then
  DEGRADE GRACEFULLY (return a safe "ask something more specific" answer) — never raise on a model
  response. LESSONS: (1) size a structured-output token budget for the WORST-CASE answer, and
  remember thinking shares it; (2) NEVER let json.loads on an LLM response crash the user path —
  always guard + degrade; (3) a filtering pipe (`| grep`) HID the tracebacks for two whole runs and
  made a crash look like a clean 5-anchor result — when a loop "completes" with suspiciously short
  output, re-run UNFILTERED before trusting it.

- **The measurement paid for itself twice.** Beyond the for-the-record number (~98% mean, 98/100/96
  over 3 passes on the corrected 47-condition set), running the FULL set surfaced the truncation
  crash that the per-anchor spot-checks never hit (they didn't run BQ6 back-to-back under the same
  process). Exhaustive runs find integration bugs that targeted ones miss.

## Session 2026-07-14 (cont.) — ceased-condition correctness + API resilience

- **Grounding protected correctness; ranking did not.** The corpus carries 7 SPENT conditions (their
  own 2025 text says "cease to have effect on <past date>": 28A/28AA/37/45/32A/22B/24A), all UNMAPPED
  by temporal. The scary risk — presenting spent law as current — did NOT happen: grounded synthesis
  reads the cease clause and states the historic dates. But spent conditions are keyword-rich and were
  OUT-RANKING the current equivalent (28A/28AA crowded out the live charge cap 28AD, which got missed).
  Fix = DEMOTE (stable, not remove) the 7 spent conditions below current ones before the top-k cut:
  still retrievable (grounding flags them; historic queries find them), never leading. Lesson: for a
  time-versioned corpus, "is it retrievable?" and "should it rank first?" are different questions —
  dead-but-embedded content needs down-ranking even when grounding stops it being mis-stated.
- **Cost-driven robustness: retry transient 503s in the pipeline.** The recurring "grammar compilation
  temporarily unavailable" 503s were aborting whole 31-case runs (wasting real money) and would crash a
  live answer. Added _create_retry() with backoff around plan()+synthesize() — the re-run rode out the
  same 503s that killed the first attempt. Resilience isn't just uptime; here it's directly a COST fix
  (no more wasted partial runs) and a live crash-fix.
- **Exonerate a change with the $0 diff, not a re-run.** When P1 false-refused in the gate, the earlier
  local ($0) retrieval-diff had already shown P1 was NOT among the 7 cases the demotion changed — so the
  change provably couldn't cause it. A 2-run P1 recheck (cheap) confirmed flicker. Reason from the
  cheap evidence before spending on a full re-run.

## Session 2026-07-14 (close) — calibration, cost, and privacy on a public repo

- **"Over-broadening" was gold-calibration, not a system bug.** BQ11/BQ14 (near-narrow anchors) looked
  like they over-cited — but the extra citations were largely DEFENSIBLE (fair treatment genuinely
  spans the consumer-protection suite; an info-service question spans billing/PSR/consumption info).
  The tight gold overstated the problem. Fix = widen Borderline (re-scored from EXISTING runs, $0),
  NOT tighten synthesis (which over-corrected during DEPTH). When a metric looks bad, check whether
  the GOLD is wrong before "fixing" the system — the 4th time this session that a gap was gold, not code.

- **Cost is a first-class constraint (Scott pays per run).** Adopted: re-score existing outputs when
  only the gold changes ($0); diagnose with LOCAL harnesses (rank probes / context-level / retrieval
  diffs) before any Opus; reserve the full 31-case + judge for real ship-gates; default 1 pass; ask
  before expensive runs. Also EXONERATE a change with the cheap diff before re-running — P1's gate
  refusal was cleared by the $0 retrieval-diff (P1 wasn't in the changed set) + a 2-call recheck, not
  a full re-run. See memory [[cost-conscious-evals]].

- **"Commit but keep private" on a PUBLIC repo = a local-only branch, never a local commit on main.**
  A local commit on main leaks the moment the next `git push origin main` runs. The plain-language
  explainer (copy-risk) went on a local-only branch `private-docs` (no upstream, absent from main's
  working tree by design). Publishing is irreversible (git history + GitHub cache), so default to the
  safe side and flag the tension rather than guessing. See memory [[private-docs-branch]].

## BREADTH batch 1 (temporal mapping 5 → 9 conditions) — lessons 2026-07-16
- **Verify a candidate date against the actual HELD TEXT, not just the modification history.** 31H's
  supplied change date (11 Feb 2019) predated our earliest held consolidation (v2019 = 3 Aug 2019),
  so it was already baked in and NOT demonstrable. The change we could actually show gap-free was a
  DIFFERENT, later one (CEP billing transparency, 31 Dec 2020 — same SI as 21B). A $0 word-level diff
  of v2019 vs v2022 surfaced the real change and its EU-directive fingerprint before any spend.
- **A condition can be introduced AND text-changed (27A).** Don't assume "introduced" = pure
  existence boundary. 27A was introduced 15 Dec 2020 AND text-changed 8 Nov 2023 (involuntary-PPM
  credit, the same reform as Cond 28). It needed a TEXT_CHANGES entry with an `introduced` marker, not
  a MAPPED entry (MAPPED asserts "current text applies" — wrong for the pre-change middle segment).
- **Introduced text-change conditions need existence-boundary semantics before introduction.** For a
  pre-introduction date, `version_for` must serve CURRENT text (like 25E/4D) so the model states
  "did not exist, introduced [date]" — returning None made synthesis refuse with an empty answer.
  Fixed with an `introduced`-aware branch; blast radius provably limited to introduced TEXT_CHANGES.
- **Crowded retrieval can arbitrate an existence-boundary fact away (T13).** "What ongoing fit and
  proper requirements must a supplier meet?" pulled a pack of related conditions (34/45A/4), and
  synthesis flickered between refusing and answering-without-citing-4C — losing 4C's introduction
  fact. An ISOLATING phrasing ("does a licensee have to remain fit and proper on an ongoing basis?")
  gave the clean "4C introduced 18 Mar 2021" answer. The mapping was sound; the crowded question
  tested scope-arbitration, not the map. Fix the eval phrasing to test what the case is FOR — and log
  the crowded-topic edge as a real (low-priority) product limitation, don't hide it.
- **Batching the ship-gate paid off:** one 40-case regression + faithfulness run verified all four
  new conditions together (decision 40/40, faithfulness 36/36, version 12/12, 0 false refusals) —
  instead of four separate ~$5 runs. Do the $0 local logic/retrieval/diff checks per condition, then
  ONE gate for the batch.

## Answer-format change — lessons 2026-07-16
- **Readability and correctness are not a trade-off — separate CONTENT from LAYOUT.** The model
  supplies grounded content (headline, plain-language headings, glossed detail); the APP supplies the
  template layout AND the version/effective dates (from the temporal map, grounded by construction).
  Rendering dates deterministically instead of asking the model to echo them fixed a flicker that had
  been "deferred" for weeks (content_checks 17-18/19 → 19/19).
- **A pure presentation change can still regress BEHAVIOUR via the prompt.** Adding headline/plain-
  language/obligation-block instructions tipped the fragile before-introduction case (27A as-of-2019)
  from a correct existence-boundary answer into a FALSE REFUSAL. The faithfulness gate was clean, but
  the decision gate caught it. Always run the full refusal+temporal suite after a synthesis-prompt edit.
- **Fix the fragility, don't just fix the eval.** The before-intro path had flickered before (T13).
  Rather than reword cases again, added an explicit EXISTENCE BOUNDARY rule ("did not exist as of X" is
  a grounded ANSWER, not a refusal) → T10/T13/T15 deterministic over 2 passes. Gated tightly to the
  temporal existence-boundary case so genuine out-of-scope refusals (R1/R2/D1/S4) are untouched.
- **Hold the push when the gate surfaces something, even under "push it live".** A synthesis-prompt
  change is exactly the kind that can drift; the discipline is measure → diagnose → fix → re-gate →
  ship, not ship-on-request. The extra gate ($ ~6) beat shipping a visible false-refusal flicker.
- **An always-on caveat is not honesty — it is noise.** The broad-answer footer said "may not be
  exhaustive" on EVERY broad answer (prompt: "Always set exhaustiveness_note..."). Because it never
  varied it carried zero signal — identical at 5/5 recall and at 2/5 — so it taught users to ignore it
  while underselling measured ~98% broad-anchor Core recall. A caveat only informs if it can be absent.
  Replaced with an EARNED hedge: confident default, hedge only on real evidence of incompleteness.
- **The model must not assert facts about OUR OWN pipeline.** How much of the licence RIA read is a
  property of retrieval, not of the extracts — the model cannot know it, so it was guessing in prose.
  Same category error as the version dates. Fix is the same split: content from the model, facts from
  code (`union_truncated` + a corpus-derived condition count). Removed the field from GROUPED_SCHEMA
  entirely rather than asking the model nicely not to author it.
- **Check whether a proposed signal can ever fire BEFORE building on it.** "Union saturated" looked
  like an obvious hedge trigger, but arithmetic said MAX_SUBQUERIES(6) * K_PER(6) = 36 unique < BUDGET
  (40) — impossible without hint sub-queries. A cheap probe over the 20 anchors confirmed it fires
  1/20 (BQ8 tariffs: 2 hints → 8 subs → 44 unique). Rare-but-real was the right answer; a signal that
  fired 0/20 would have been decorative honesty. Measure the trigger, not just the fix.
- **String tests can pass while the feature is broken for the user.** The copy-out button's text was
  verified hard ($0, assertions on markers/question/as-of/Source lines/disclaimer) and was correct
  every time — meanwhile the FEATURE was unusable: the label promised a copy it didn't perform, the
  instruction sat below the box, and `st.code`'s default `height="content"` grew the box to the full
  answer length so its top-right copy icon scrolled out of view ("the icon disappeared"). Three UI
  judgements made without ever seeing the thing rendered; two were wrong. Testing the OUTPUT is not
  testing the INTERACTION. For UI, someone has to actually click it — Scott found all three in seconds.
- **A control's label must name what it DOES, not what it's about.** "📋 Copy question and answer" was
  an expander: clicking it revealed a box. The user reasonably read the chevron + label as two controls
  doing the same thing, and read "clicked Copy, nothing copied" as broken software. Renamed to describe
  what it REVEALS ("Plain-text version … - to copy") so the copy icon inside is the only thing
  promising a copy. One promise per control.
- **"It works" from a spot-check isn't confirmation the feature works.** Asked whether the copy icon
  was present, the answer was yes — on a SHORT answer. That was taken as the feature being sound, and
  a caption was shipped on top of an unnoticed layout bug that only manifests on LONG (broad) answers.
  Confirmations are only as broad as the case they were tested on; ask which case was checked.
- **Ship what isn't gated, gate what is — but only if the split is honest.** The copy button shared a
  FILE with the gate-blocked chrome claim, not a dependency (evals never touch `app/main.py`). Splitting
  it out (revert chrome → commit UI alone → verify the diff is purely additive → push → reinstate) let
  three UI fixes ship live while `src/planner.py` stayed correctly unshipped. File-coupling is not
  logical coupling — but check the diff, don't assume it.
- **A similarity threshold is the wrong instrument for change detection — it scales with LENGTH.**
  `detect_changes.py` called an interval "changed" when normalized similarity fell below 0.97. That
  hid 29 of 86 real changes across five snapshots, because one deleted sentence in a long condition
  scores ~0.99. Two of the hidden ones mattered: 31G (0.988) DELETED the dormancy caveat on 31G.3A —
  the edit that ACTIVATED a live 24/7 obligation; and 28 (0.973) gained paragraph (bb). No higher
  number fixes this: the same edit scores differently in a short vs long condition. The right rule is
  EXACT inequality on normalized text — `norm()` already strips every non-alphanumeric char, so PDF
  noise ("relatio n", "electricitycaused") is gone before comparison and any residual difference is
  real text. Keep the ratio as a MAGNITUDE hint only, and flag small edits rather than dropping them.
- **A "verified" comment is only as trustworthy as the tool that verified it — so record the TOOL.**
  `temporal.py` and `provenance.md` both asserted "Condition 28 unchanged 2019→2022". Both were
  written in good faith from the change-map, and both were false, so 28's first segment spanned two
  different texts and served 2019-2020 queries a paragraph citing SLC 27A before 27A existed. When a
  curation tool is fixed, every downstream claim it produced becomes suspect — re-audit, don't assume.
  The re-audit of all 9 mapped conditions found 28 (real defect) + 4D (3 grammatical errata, benign)
  and CONFIRMED the other 7, which is also the value: the same method that finds bugs earns trust.
- **Impossible-looking data means your comparison is wrong, not that reality is strange.** A diff
  showed Condition 24 changing and then reverting to a byte-identical earlier hash. Regulatory text
  does not do that. Cause: comparing stored CHUNKS (windowed with 25-word overlap, so re-joining
  duplicates words) against freshly-parsed PDF text. Every "change" sat exactly at a data-source
  boundary — the tell. Compare like with like, and treat a physically implausible result as a bug in
  the instrument. Chasing it as if real would have produced a confidently wrong mapping.
- **Web servers don't list directories — use the Wayback CDX API to enumerate.** Trying to browse
  `ofgem.gov.uk/sites/default/files/` 404s by design; you can only fetch a file whose exact name you
  already know. `web.archive.org/cdx/search/cdx?url=<path>&matchType=prefix&fl=original` enumerates
  everything ever crawled. `collapse=digest` on a SINGLE url lists every distinct VERSION of that file
  — which is how two intermediate consolidations (1 Jul 2024, 1 Oct 2024) surfaced.
- **A "Current" URL is a moving target; a dated URL is a snapshot.** Ofgem's `.../2023-03/…- Current.pdf`
  is overwritten in place — it now serves the Aug 2025 text, so the `2023-03` in the path means only
  when the pointer was created. That is why the project chose dated PDFs for reproducibility. Useful
  corollary: because it IS overwritten, the archive holds the older texts it used to serve.
- **Inference that turns out RIGHT is still not evidence.** Paragraph (bb) cites SLC 27A, so 15 Dec 2020
  (27A's introduction) was the obvious insertion date — and it was correct, confirmed by Ofgem's s.11A
  notice modifying 27, 28 and introducing 27A in one package. But inference of exactly this kind
  ("verified unchanged") is what created the defect. Being right by luck and right by evidence look
  identical afterwards; only one of them is repeatable. Get the notice.
- **A derived binary artefact committed to git is a scaling trap — commit the SOURCE, rebuild the
  cache.** RIA commits its ChromaDB vector store (`chroma.sqlite3` + HNSW `.bin` dirs) so the deployed
  app has it. That worked at 3 versions; at 5 electricity versions it is 58.9MB, and GitHub REJECTS
  (not just warns) any file over 100MB per push. The store grows along both axes RIA expands on —
  temporal versions AND a future gas corpus — so the limit is arithmetic, not bad luck. The tell: the
  8.6MB `slc_chunks.jsonl` (plain TEXT, the real source of truth) scales far better than the 59MB
  binary DERIVED from it. Lesson for any RAG/embeddings project: treat the vector store as a
  build-time cache, not a committed asset — commit the chunks, rebuild embeddings on deploy (or host
  the store externally). Decide this BEFORE the corpus grows, because migrating a committed-binary
  history later means rewriting it or carrying LFS.
- **When embed.py deletes+recreates a collection, the old HNSW uuid dir is orphaned — commit a
  CONSISTENT store.** A rebuild leaves a new `chroma/<uuid>/` dir (untracked) and the previously-
  tracked one dead. Committing only `chroma.sqlite3` would ship an inconsistent store. Verify which
  uuid the live sqlite references (`SELECT id FROM segments`), git-add the live dir, git-rm the
  orphan. Don't assume `git add chroma/` DTRT.
- **A correctness fix can break a downstream consumer that hard-coded the OLD data shape.** Splitting
  Condition 28 from 2 segments to 3 (a correct temporal fix) broke the version-history PANEL, which
  assumed "one change = first-vs-last diff, labelled with the first change date." The answer stayed
  correct; the panel started mis-dating a change — the exact failure the temporal feature exists to
  prevent, arriving through a presentation helper. Lesson: when you generalise a data structure
  (N=2 → N≥2), grep every consumer of the old cardinality assumption BEFORE shipping, not after a
  screenshot. The consumers of a "timeline" are the first place a two-becomes-three bug hides.
- **A check that asserts "a thing of the right TYPE exists" gives false confidence — assert the
  invariant that matters.** The eval's history_check verified a version-history view of the expected
  KIND was produced; it passed 6/6 while the panel mislabelled its diff, because it never read the
  date or the diff. "Green" meant "a panel exists," not "the panel is right." Shallow existence/type
  checks are worse than no check: they actively signal safety. Strengthened it to assert the
  semantic invariant (the labelled change == the change the diff brackets == a real timeline marker),
  re-derived deterministically ($0). Rule: a check should fail on the bug you actually fear, and you
  should PROVE it does by feeding it the broken input.
- **Match the verification to the blast radius, not to habit.** Reflex said "shipped pipeline change
  → full 41-case API gate." But the history-panel fix is a try/except-wrapped presentation helper
  outside the answer path — it cannot move a decision, citation, refusal, or served version. A full
  Opus-planning+synthesis+judge regression would have spent real money re-testing things the change
  can't touch, AND couldn't have caught the bug anyway (the history_check was type-only). The right
  verification was a deterministic $0 test of history.py directly — more thorough for THIS change
  than the API suite, and free. Ask "what can this change actually break?" before reaching for the gate.
- **Harden the TEST HARNESS like production — a crash in the grader discards evidence.** The eval's
  faithfulness judge ran at max_tokens=1024 WITH adaptive thinking (shares the budget), so a long
  answer truncated its JSON and a bare json.loads crashed the ENTIRE 44-case run before any results
  were written. It was the exact truncation-crash class we'd already fixed in the serving path
  (planner.py, 7f13b84) — the fix just never got applied to the harness. A grader that can crash is
  as costly as a product that can crash: it throws away a full run's spend and evidence. Same
  discipline both sides — real token headroom, retry, degrade-don't-die (faithful=None, excluded from
  the count), and SURFACE the degradation (judge_unparsed) so it's never a silent drop.
- **When you generalise a data structure, its downstream consumers include the EVAL that checks it.**
  Today's Condition 28 fix (2→3 segments) needed fixes in three places that assumed "one change":
  history.py (the panel), and — a step removed — the eval's history check was too shallow to notice.
  Mapping 31G (also 3 segments) then rode on all of it. The lesson compounds: a cardinality change
  ripples through the panel, the grader, AND any later mapping of the same shape. Grep every consumer,
  including the tests.
