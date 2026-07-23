"""
Phase 7 — Corpus-aware query planner (broad-query completeness).

Turns a question into 1..N focused SEARCH sub-queries so a BROAD question ("what obligations do
we have to vulnerable customers?") retrieves ALL the relevant conditions, not just the best match,
while a SPECIFIC question stays a single query (no behaviour change vs today).

Corpus-aware: first a wide-net retrieve gets the candidate conditions that actually EXIST in the
corpus; their titles are shown to the planner so its sub-queries use the licence's own vocabulary
and cover the surfaced obligation areas. The original question is ALWAYS kept as a sub-query, so
planning can only ADD coverage — never regress below today's single-query behaviour.

Baseline (Step 0) showed a targeted sub-query reaches conditions a broad query structurally can't
(e.g. "back-billing" finds Cond 21BA where "billing obligations" misses it even at depth 40) —
that is exactly what this planner exploits.

CLI smoke test:  venv/bin/python src/planner.py "what obligations do we have to vulnerable customers?"
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date

try:  # works both as `src.planner` (app/evals) and `python src/planner.py`
    from src import rag
except ImportError:
    import rag

try:
    import anthropic
except ImportError:
    anthropic = None

# Transient API errors (503 'overloaded' / grammar-compilation-unavailable, rate limits, connection
# drops) were aborting whole eval runs AND would crash a live answer. Retry in place with backoff on
# TOP of the SDK's own retries, so a brief blip is ridden out instead of raising.
_RETRYABLE = tuple(e for e in (
    getattr(anthropic, "InternalServerError", None),
    getattr(anthropic, "APIConnectionError", None),
    getattr(anthropic, "APITimeoutError", None),
    getattr(anthropic, "RateLimitError", None),
) if e) if anthropic else ()


def _create_retry(client, kwargs, attempts: int = 4):
    delay = 2.0
    for i in range(attempts):
        try:
            return client.messages.create(**kwargs)
        except _RETRYABLE:
            if i == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2

WIDE_NET = 40          # depth of the wide-net retrieve that builds the candidate landscape
MAX_CANDIDATES = 25    # cap candidate conditions shown to the planner (keeps the prompt small)
MAX_SUBQUERIES = 6     # total sub-queries incl. the original (bounds cost/latency + precision drift)

# Deterministic safety net for well-known SPECIFIC obligations that the LLM planner reaches
# unreliably. Some conditions only rank into the top-k under an exact short term and the planner
# tends to dilute it (e.g. 21A "annual statement of supply" ranks #3 for 'annual statement' but
# DROPS OUT entirely once 'domestic'/'consumption' qualifiers are appended). For a BROAD question
# whose area matches, we inject these PROVEN phrasings verbatim as extra sub-queries — additive, so
# they never displace the planner's own coverage. Each phrasing is verified by a retrieval rank
# probe (scratchpad), not guessed. Curated + extensible by design: reliability over LLM generalisation.
SPECIFIC_OBLIGATION_HINTS = [
    {
        "area": "billing",
        # SPECIFIC terms only, matched against the QUESTION alone (not candidate titles). Generic
        # words ('bill', 'statement', 'charge') and candidate-title matching over-fired: they
        # injected billing sub-queries into non-billing questions (a disconnection Q with "unpaid
        # bill"; a Guaranteed-Standards Q whose candidates happened to include billing conditions),
        # displacing the real extracts and causing false refusals. Under-firing is safe (degrades
        # to the normal planner); over-firing breaks unrelated questions.
        "triggers": ("billing", "back-billing", "backbilling"),
        # "Backbilling" -> Cond 21BA (a genuine domestic back-billing time-limit obligation the LLM
        # planner reaches unreliably). NOTE: an earlier "annual statement" hint was dropped — it only
        # fetched Cond 21A, whose text is the CRC Energy Efficiency Scheme statement to NON-domestic
        # Participants (out of scope for domestic billing); synthesis correctly ignored it anyway.
        "queries": ["Backbilling"],   # -> 21BA rank ~1
    },
    {
        "area": "tariffs",
        # Same pattern as billing: for a broad tariffs/prices question the planner reaches Cond 25
        # (comparability) fine but MISSES 22A (Unit Rate/Standing Charge/Tariff Name) and 31I
        # (price-change notifications) — both rank into top-k only under an exact short term the
        # planner won't produce. Trigger matched against the QUESTION only. "tariff" alone OVER-FIRED
        # (an over-fire test vs all 20 anchors + the 31-case suite showed it also hit BQ18
        # environmental-claims, BQ19 Feed-in-Tariffs, O3/P6 fixed-term-ending — wrong sub-areas that
        # could be displaced). Narrowed to specific licence terms + "prices": fires BQ8 alone, 0
        # collateral ("prices" does not match "price cap"). Under-fire is safe; over-fire breaks.
        "triggers": ("unit rate", "standing charge", "prices"),
        "queries": ["Unit Rate Standing Charge", "contract changes information price change"],  # -> 22A #1, 31I #1
    },
]

# Planner runs on Haiku (synthesis stays on Opus). A/B (evals/planner_ab.py) showed Haiku planning
# matches Opus on anchor Core recall (16/17 both), so this cuts per-query cost with no quality loss.
HAIKU = "claude-haiku-4-5-20251001"
PLANNER_MODEL = HAIKU

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "is_broad": {"type": "boolean"},
        "subqueries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "focus": {"type": "string"},   # short obligation-area label
                    "query": {"type": "string"},   # focused, keyword-rich search phrase
                },
                "required": ["focus", "query"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["is_broad", "subqueries"],
    "additionalProperties": False,
}

PLAN_SYSTEM = (
    "You are a retrieval planner for a RAG assistant grounded ONLY in Ofgem electricity supply "
    "Standard Licence Conditions. Given a user question and the candidate licence conditions that "
    "exist in the corpus, produce focused SEARCH sub-queries that together retrieve EVERY relevant "
    "obligation.\n"
    "Rules:\n"
    "- If the question is SPECIFIC (about one thing), set is_broad=false and return exactly ONE "
    "sub-query that restates it. Do NOT broaden a specific question.\n"
    "- If the question is BROAD (asks for obligations / duties / responsibilities across an area), "
    "set is_broad=true and decompose into one focused sub-query PER distinct obligation area. Use "
    "the candidate condition TITLES to phrase sub-queries in the licence's own vocabulary.\n"
    "- IMPORTANT: the candidate list is what a single broad search happened to surface — it is NOT "
    "exhaustive. For a broad question, ALSO add sub-queries for well-known SPECIFIC obligations in "
    "the area that you are confident the licence covers, even if absent from the candidates (e.g. for "
    "billing: back-billing time limits, the annual statement of consumption; for disconnection: the "
    "winter / vulnerability moratorium). Phrase them as the licence would (the specific mechanism, not "
    "the lay term). Do NOT invent obligations that plainly do not exist.\n"
    f"- Return at most {MAX_SUBQUERIES - 1} sub-queries (the original question is added separately). "
    "Prefer precision: only areas genuinely responsive to the question.\n"
    "- Each 'query' is a short keyword-rich search phrase, not a sentence."
)


def _candidate_conditions(question: str, coll) -> list[tuple[str, str]]:
    """Wide-net retrieve → ordered unique (condition, title) pairs that exist in the corpus."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(cond: str, title: str) -> None:
        if cond not in seen:
            seen.add(cond)
            pairs.append((cond, title))

    for h in rag.vector_retrieve(question, WIDE_NET, coll):
        add(h["meta"]["condition"], h["meta"]["condition_title"])
    bm25, ids, cbi = rag.get_bm25()
    scores = bm25.get_scores(rag.expand_query(question))
    top = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)[:WIDE_NET]
    for i in top:
        m = cbi[ids[i]]["metadata"]
        add(m["condition"], m["condition_title"])
    return pairs[:MAX_CANDIDATES]


def _hint_subqueries(question: str, candidates: list[tuple[str, str]]) -> list[str]:
    """Proven-phrasing sub-queries to inject for a BROAD question whose area matches a curated
    hint (see SPECIFIC_OBLIGATION_HINTS). Matches trigger keywords against the QUESTION ONLY —
    matching candidate titles over-fired (a question with no billing intent whose wide-net
    candidates merely included billing conditions would wrongly trigger). `candidates` is kept in
    the signature for future hints that may need it."""
    hay = question.lower()
    out, seen = [], set()
    for h in SPECIFIC_OBLIGATION_HINTS:
        if any(k in hay for k in h["triggers"]):
            for q in h["queries"]:
                if q.lower() not in seen:
                    seen.add(q.lower())
                    out.append(q)
    return out


def plan(question: str, coll=None, client=None, model: str | None = None) -> dict:
    """Return {'is_broad': bool, 'subqueries': [str, ...]} — sub-queries ALWAYS include the
    original question first. Specific question → [question]; broad → several focused phrases."""
    coll = coll or rag.get_collection()
    model = model or PLANNER_MODEL
    client = client or rag.get_client()

    candidates = _candidate_conditions(question, coll)
    cand_str = "\n".join(f"- Condition {c}: {t}" for c, t in candidates)
    user = f"Question: {question}\n\nCandidate conditions in the corpus:\n{cand_str}"

    fmt = {"type": "json_schema", "schema": PLAN_SCHEMA}
    kwargs = dict(model=model, max_tokens=1024, system=PLAN_SYSTEM,
                  messages=[{"role": "user", "content": user}])
    if "haiku" in model:
        kwargs["output_config"] = {"format": fmt}
    else:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": "low", "format": fmt}
    resp = _create_retry(client, kwargs)
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    # Original question ALWAYS first (safety net — planning can only add coverage). For a broad
    # question, inject the deterministic hint sub-queries next (proven phrasings for hard-to-reach
    # specific obligations), THEN the planner's focused sub-queries. Hints are ADDITIVE: the cap is
    # raised by the number injected so they never displace the planner's own coverage. Dedup
    # case-insensitively (a hint the planner already emitted is not duplicated).
    is_broad = bool(data.get("is_broad"))
    hints = _hint_subqueries(question, candidates) if is_broad else []
    ordered = [question] + hints + [(sq.get("query") or "").strip() for sq in data.get("subqueries", [])]
    cap = MAX_SUBQUERIES + len(hints)
    subs, seen = [], set()
    for q in ordered:
        key = q.lower()
        if q and key not in seen:
            seen.add(key)
            subs.append(q)
        if len(subs) >= cap:
            break
    return {"is_broad": is_broad, "subqueries": subs}


K_PER = 6       # chunks pulled per sub-query (reuses the existing hybrid retriever)
BUDGET = 40     # max unique chunks in the union fed to synthesis (context/cost cap)

_COND_COUNT: int | None = None


def condition_count(coll=None) -> int:
    """How many distinct conditions the CURRENT version of the corpus holds. Derived from the store
    (never hardcoded) so it self-updates with the corpus, and cached — one metadata read per process."""
    global _COND_COUNT
    if _COND_COUNT is None:
        coll = coll or rag.get_collection()
        got = coll.get(where={"version_label": rag.versions.CURRENT_LABEL}, include=["metadatas"])
        _COND_COUNT = len({m["condition"] for m in got["metadatas"]})
    return _COND_COUNT


def plan_and_retrieve(question: str, coll=None, client=None, model: str | None = None,
                      k_per: int = K_PER, budget: int = BUDGET) -> tuple[dict, list[dict]]:
    """Plan sub-queries, retrieve each via the existing hybrid retriever, then UNION + dedup by
    chunk id with ROUND-ROBIN interleave across sub-queries: each obligation area contributes its
    rank-1 chunk before any contributes its rank-2, so the budget cap can't starve a whole area.
    Returns (plan, union_chunks). A specific question → one sub-query → behaves like today.

    Also sets p["union_truncated"]: True only when the sub-queries surfaced MORE unique chunks than
    the budget could carry, i.e. we genuinely did not read everything we found. This is the ONLY
    runtime evidence that an answer might be incomplete, so it is the only thing that earns a
    completeness hedge in the footer. It is rare by construction — without hint sub-queries the
    ceiling is MAX_SUBQUERIES * K_PER = 36 unique, below BUDGET — so it fires only on hint-boosted
    questions (measured: 1 of the 20 broad anchors, BQ8 tariffs at 8 sub-queries / 44 unique)."""
    coll = coll or rag.get_collection()
    p = plan(question, coll=coll, client=client, model=model)
    lists = [rag.hybrid_retrieve(sq, k_per, coll)[0] for sq in p["subqueries"]]
    p["union_truncated"] = len({c["id"] for lst in lists for c in lst}) > budget
    union: list[dict] = []
    seen: set[str] = set()
    maxlen = max((len(lst) for lst in lists), default=0)
    for depth in range(maxlen):
        for lst in lists:
            if depth < len(lst):
                c = lst[depth]
                if c["id"] not in seen:
                    seen.add(c["id"])
                    union.append(c)
                    if len(union) >= budget:
                        return p, union
    return p, union


# --- Step 3: grouped-by-obligation synthesis ------------------------------------------------
# Reuse rag.SYSTEM's grounding + temporal rules VERBATIM (so Phase 7 composes with version
# awareness), swapping only the output-format instruction and the empty-answer wording.
_GROUPED_TAIL = (
    "Produce a SCANNABLE, plain-English answer. "
    "HEADLINE: set `headline` to ONE plain-English sentence that answers the question directly at a "
    "glance, in everyday words, supported by the obligations below. It must contain no figure, age, "
    "date, monetary amount, or threshold that is not in the extracts. On a refusal set headline to an "
    "empty string. "
    "Then structure the answer as a list of DISTINCT OBLIGATIONS. Each obligation is one concrete duty: "
    "`obligation` — a short heading in PLAIN LANGUAGE saying WHAT THE SUPPLIER MUST DO in everyday "
    "words (NOT the condition number, NOT bare licence jargon); `detail` — a 2-4 sentence plain-English "
    "explanation drawn ONLY from the extracts; and citation(s) to the condition(s) it comes from "
    "(condition number, title, page range). Explain in plain English FIRST; when you use a licence "
    "DEFINED TERM, gloss it briefly on first use using ONLY the definition given in the extracts — do "
    "not invent a definition, and if the extracts do not define it, use the term without inventing a "
    "gloss. Group related points under a single obligation; keep obligations distinct (do not split one "
    "duty across several, or merge unrelated duties). "
    "CITATION COMPLETENESS: when a grouped obligation draws on several DIFFERENT licence conditions "
    "that each impose a distinct duty, cite EVERY such condition — never collapse several distinct "
    "conditions into one representative citation. Every condition among the extracts that MATERIALLY "
    "addresses the question must appear in at least one obligation's citations; a condition that is only "
    "tangential need not be cited. "
    "Include an obligation ONLY if the extracts support it — do "
    "NOT pad with tangential conditions that merely appeared among the extracts. "
    "SCOPE DISCIPLINE. The extracts come from a BROAD search and may include conditions only "
    "tangentially related to the question; answer only what these Electricity Supply licence "
    "conditions actually address. "
    "(1) If the question's CORE subject is a regime/instrument NOT in these conditions (e.g. the "
    "Guaranteed Standards of Performance and their compensation, the Ombudsman complaint-handling "
    "process, gas supply, or a specific numeric price-cap level) and the extracts touch it only "
    "tangentially, do NOT answer it from a loosely-related condition: set refused=true, "
    "obligations=[], and say so in reason. "
    "(2) If the question is COMPOUND — it asks about several things and only SOME are covered here — "
    "answer the covered parts as obligations AND set out_of_scope_note to name the part(s) these "
    "licence conditions do NOT cover (e.g. 'Guaranteed Standards compensation for a missed switch is "
    "not set by these licence conditions'). Never let a tangential in-scope obligation silently stand "
    "in for the out-of-scope part. "
    "(3) Set out_of_scope_note to an empty string when the whole question is fully in scope. "
    "EXISTENCE BOUNDARY (do NOT refuse): if the temporal facts state a retrieved condition did NOT yet "
    "exist as of the as-of date, that is KNOWN territory, not a gap — ANSWER it. Give a headline and a "
    "single obligation block that states plainly the obligation did not exist as of that date and the "
    "date it was introduced (from the temporal facts), and cite that condition. Do NOT set refused=true "
    "merely because the condition post-dates the as-of date, and do NOT present its current text as "
    "having applied then. "
    "NO UNEARNED SPECIFICS: never introduce a specific number, age, monetary amount, or threshold that "
    "is not in the extracts; if the licence gives a category or a qualitative test rather than a figure, "
    "state it that way. If any part of the answer cannot be confirmed from the extracts, say so plainly "
    "rather than filling the gap. "
    "If the extracts contain nothing adequate, set refused=true, headline='', obligations=[], and say "
    "what was missing in reason. Return your response in the required structured format."
)
GROUPED_SYSTEM = (
    rag.SYSTEM.rsplit("Return your response", 1)[0].rstrip().replace("leave answer empty", "leave obligations empty")
    + "\n\n" + _GROUPED_TAIL
)

GROUPED_SCHEMA = {
    "type": "object",
    "properties": {
        "refused": {"type": "boolean"},
        "headline": {"type": "string"},
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "obligation": {"type": "string"},
                    "detail": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "condition": {"type": "string"},
                                "condition_title": {"type": "string"},
                                "pages": {"type": "string"},
                            },
                            "required": ["condition", "condition_title", "pages"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["obligation", "detail", "citations"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string"},
        # NOTE: no exhaustiveness_note here ON PURPOSE. How much of the licence RIA actually read is a
        # fact about OUR retrieval, not about the extracts — the model cannot know it, so it must not
        # author it. It is rendered deterministically in the footer from `union_truncated` (same
        # content-from-model / facts-from-code split as the version dates).
        "out_of_scope_note": {"type": "string"},
    },
    "required": ["refused", "headline", "obligations", "reason", "out_of_scope_note"],
    "additionalProperties": False,
}


def synthesize(question: str, union_chunks: list[dict], coll=None, as_of: date | None = None,
               client=None, model: str | None = None, is_broad: bool = False,
               union_truncated: bool = False) -> dict:
    """Grounded, grouped-by-obligation synthesis over the union chunks. Returns the grouped result
    PLUS backward-compatible `answer` (markdown) + `citations` (deduped) so the existing UI / evals
    / temporal-history consumers keep working unchanged."""
    coll = coll or rag.get_collection()
    as_of = as_of or date.today()
    model = model or rag.MODEL
    client = client or rag.get_client()

    conds = {c["meta"]["condition"] for c in union_chunks}
    context = rag.build_context(rag.expand_hits(union_chunks, coll, as_of))
    notes = rag.temporal.temporal_notes(conds, as_of) + rag.temporal.text_change_notes(conds, as_of)
    parts = [
        f"Current licence version: consolidated to {rag.temporal.current_version_str()}.",
        f"As-of date: {rag.temporal.fmt(as_of)}",
    ]
    scope = rag.temporal.scope_note(as_of)
    if scope:
        parts.append(scope)
    if notes:
        parts.append("Temporal facts (authoritative):\n" + "\n".join(f"- {n}" for n in notes))
    parts.append(f"Question: {question}")
    parts.append(f"Retrieved extracts:\n\n{context}")
    user_content = "\n\n".join(parts)

    fmt = {"type": "json_schema", "schema": GROUPED_SCHEMA}

    def _make_kwargs(max_tokens):
        kw = dict(model=model, max_tokens=max_tokens, system=GROUPED_SYSTEM,
                  messages=[{"role": "user", "content": user_content}])
        if "haiku" in model:
            kw["output_config"] = {"format": fmt}
        else:
            kw["thinking"] = {"type": "adaptive"}
            kw["output_config"] = {"effort": "medium", "format": fmt}
        return kw

    # A broad answer can be long, and with adaptive thinking the thinking tokens share the
    # max_tokens budget — so a too-small budget makes the response stop mid-JSON (stop_reason
    # 'max_tokens'), which then fails json.loads and USED TO CRASH the whole answer (seen live on a
    # prepayment question). Give it real room (8192), retry once bigger (16384) on truncation or a
    # malformed parse, then DEGRADE GRACEFULLY — never raise.
    result = None
    for max_tokens in (8192, 16384):
        resp = _create_retry(client, _make_kwargs(max_tokens))
        if resp.stop_reason == "refusal":
            return {"refused": True, "obligations": [], "reason": "The request was declined by a safety filter.",
                    "exhaustiveness_note": "", "out_of_scope_note": "", "citations": [], "answer": "",
                    "as_of": as_of.isoformat(), "context": context, "temporal_facts": notes, "prompt": user_content}
        text = next((b.text for b in resp.content if b.type == "text"), "")
        if resp.stop_reason != "max_tokens":          # not truncated → try to parse
            try:
                result = json.loads(text)
                break
            except json.JSONDecodeError:
                pass                                   # malformed → fall through to retry / degrade
        # else truncated → loop retries with a bigger budget
    if result is None:
        # Truncated/malformed even after retry: return a safe degraded answer, never crash.
        return {"refused": False, "obligations": [], "reason": "",
                "exhaustiveness_note": "The full answer could not be generated (the response was too long to complete). Please ask about a more specific obligation.",
                "out_of_scope_note": "", "citations": [], "as_of": as_of.isoformat(),
                "answer": "_The full answer could not be generated for this broad question — please ask about a more specific obligation._",
                "context": context, "temporal_facts": notes, "prompt": user_content}
    obligations = result.get("obligations", [])
    # Sanitise citation condition refs to the BARE condition id + derive deduped citations.
    # The synthesis sometimes emits the condition field as "8 — Obligations under…" (id + title)
    # instead of "8". That bare-id normalisation is load-bearing, not cosmetic: the id keys the
    # version-history lookup (history.views_for) and citation_note — a malformed "8 — Title" key
    # matches no mapped condition, so the history panel silently fails to render and the effective
    # date isn't attached. Strip a stray "Condition " prefix, then keep only the leading id
    # (digits + optional letters, e.g. 8 / 31G / 27A / 0A); the title already lives in condition_title.
    citations, seen = [], set()
    for ob in obligations:
        for ci in ob.get("citations", []):
            raw = re.sub(r"(?i)^\s*condition\s+", "", str(ci.get("condition", ""))).strip()
            m = re.match(r"(\d+[A-Z]{0,3})\b", raw)
            ci["condition"] = m.group(1) if m else raw
            if ci["condition"] and ci["condition"] not in seen:
                seen.add(ci["condition"])
                citations.append(ci)
    result["citations"] = citations

    # --- Render the scannable answer template (Answer Format Spec). The model supplies grounded
    # CONTENT (headline, plain-language headings, glossed detail); the app supplies the LAYOUT and the
    # version/effective dates (from the temporal map, grounded by construction — not model-echoed). ---
    def _source_line(ob):
        parts = []
        for ci in ob.get("citations", []):
            cond = ci["condition"]
            seg = f"Condition {cond}"
            pages = (ci.get("pages") or "").strip()
            if pages:
                seg += f" (pp. {pages})"
            vnote = rag.temporal.citation_note(cond, as_of)
            if vnote:
                seg += f" — {vnote}"
            parts.append(seg)
        return ("Source: " + "; ".join(parts)) if parts else ""

    blocks = []
    for ob in obligations:
        block = f"**{ob.get('obligation', '')}**  \n{ob.get('detail', '')}"
        src = _source_line(ob)
        if src:
            block += f"  \n{src}"
        blocks.append(block)

    headline = (result.get("headline") or "").strip()
    body_parts = ([headline] if headline else []) + blocks

    # Footer. The version line always shows (version-awareness is a selling point). The "Not covered
    # here" boundary is PROPORTIONATE: shown for broad (multi-obligation) answers or when part of the
    # question is out of scope; a simple single-obligation answer stays light.
    oos = (result.get("out_of_scope_note") or "").strip()
    footer = [
        f"_Based on: Ofgem electricity supply Standard Licence Conditions consolidated to "
        f"{rag.temporal.current_version_str()}; answer as of {rag.temporal.fmt(as_of)}._"
    ]
    # The question-specific out-of-scope / temporal caveat gets its OWN line (shown whenever present) —
    # never glued onto the generic boundary, which reads as a run-on.
    if oos:
        footer.append(f"_**Please note:** {oos.rstrip('. ')}._")
    # The generic scope boundary is proportionate: shown only on BROAD answers (planner is_broad),
    # so a narrow answer that happens to have a few facets stays light.
    if is_broad:
        footer.append(
            "_**Not covered here:** voluntary industry commitments, Ofgem guidance sitting outside the "
            "licence, and whether any given supplier is actually complying — RIA interprets the "
            "electricity supply licence, it does not verify compliance._"
        )
    # Completeness hedge (broad answers only) — EARNED, so it appears ONLY when the union genuinely
    # truncated (we found more than we could read). The old always-on "may not be exhaustive" carried
    # no signal: it fired identically at 5/5 recall and at 2/5, teaching users to ignore it while
    # underselling measured ~98% broad-anchor Core recall.
    # There is deliberately NO confident counterpart here. That RIA searches every condition is a
    # property of the SYSTEM, not of this answer — constant text repeated on every answer is wallpaper
    # whether it hedges or reassures, so it lives in the UI chrome and is stated once (app/main.py,
    # via condition_count). The footer carries only what VARIES with this answer.
    if is_broad and union_truncated and not result.get("refused"):
        ex = ("**Possibly more:** this question reached more of the licence than RIA could read in "
              "one pass, so there may be further obligations — ask about a specific area for full "
              "coverage.")
        footer.append(f"_{ex}_")
        result["exhaustiveness_note"] = ex

    result["answer"] = "" if result.get("refused") else "\n\n".join(body_parts + footer)
    result["as_of"] = as_of.isoformat()
    # Fields the existing UI / eval faithfulness-judge expect on a result.
    result["context"] = context
    result["temporal_facts"] = notes
    result["prompt"] = user_content
    return result


def answer_broad(question: str, coll=None, as_of: date | None = None, client=None,
                 model: str | None = None) -> dict:
    """Full Phase-7 pipeline: plan → union retrieve → grouped synthesis. (Step 4 wires this into
    rag.answer_question behind the out-of-scope backstop; kept thin here for isolated testing.)"""
    coll = coll or rag.get_collection()
    # Planner uses PLANNER_MODEL (Haiku); only synthesis takes `model` (Opus). Decoupled so the
    # cheap plan step doesn't inherit the expensive synthesis model.
    p, union = plan_and_retrieve(question, coll=coll, client=client)
    result = synthesize(question, union, coll=coll, as_of=as_of, client=client, model=model,
                        is_broad=bool(p.get("is_broad")),
                        union_truncated=bool(p.get("union_truncated")))
    result["plan"] = p
    result["_union"] = union   # raw union chunks so callers can build retrieval/transparency meta
    return result


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "what obligations do we have to vulnerable customers?"
    p = plan(q)
    print(f"question : {q}")
    print(f"is_broad : {p['is_broad']}")
    print(f"sub-queries ({len(p['subqueries'])}):")
    for i, s in enumerate(p["subqueries"]):
        print(f"  {i}. {s}")
