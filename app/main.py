"""
Phase 4 - Streamlit UI.

Single-turn Q&A over the Ofgem Electricity Supply Standard Licence Conditions,
wired to src.rag.answer_question(). Shows the grounded answer, condition-level
citations, a clear "not in source material" refusal state, and a collapsible
panel of the retrieved sources (transparency during the PoC).

Run: streamlit run app/main.py
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import temporal, history  # noqa: E402
from src.planner import condition_count  # noqa: E402
from src.rag import STORE, TOP_K, answer_question, get_client, get_collection  # noqa: E402

# --- Public-demo safeguards ---
MAX_PER_SESSION = 30       # questions per browser session (raised for live demos)
MAX_QUESTION_CHARS = 300   # input length cap
MAX_PER_DAY = 300          # soft global daily cap (in-memory; resets on container restart).
                           # The hard cost ceiling is the Anthropic Console spend limit.

EXAMPLES = [
    ("Back-billing limit", "Can a supplier back-bill a domestic customer for consumption more than 12 months ago?"),
    ("Max back-billing period", "What is the maximum back-billing period for domestic customers?"),
    ("Disconnection for debt", "What must we do before disconnecting a domestic customer for debt?"),
    ("Priority Services Register", "What are our Priority Services Register obligations for identifying and recording vulnerable customers?"),
    ("Blocking a switch", "Can a supplier block a customer from switching to another supplier?"),
    ("Security deposits", "What are the rules on security deposits for domestic customers?"),
    ("Out of scope ↩", "What safety certifications are required to install a domestic gas boiler?"),
]

# Broad questions — RIA plans focused sub-searches, unions the results, and answers grouped by
# obligation, so an open "what are all our duties around X?" question surfaces every relevant
# condition rather than only the closest match.
BROAD_EXAMPLES = [
    ("Vulnerable customers", "What obligations do we have to vulnerable customers?"),
    ("Billing obligations", "What are our billing obligations to domestic customers?"),
    ("Installing a smart meter", "What must we do when installing a smart meter?"),
]

# Temporal examples set the question AND a past "as of" date to showcase the time travel.
# Grouped into the three kinds of change RIA can answer across, each with its own heading.
_CCB_Q = "Do suppliers have to protect domestic customer credit balances?"
_EBSS_Q = "Can the Secretary of State direct suppliers to make Energy Bill Support Scheme payments?"
_PPM_Q = "What protections apply when a supplier installs a prepayment meter?"
_NDF_Q = "What fair-treatment obligations do suppliers have towards business customers?"
_BMR_Q = "What billing information must a supplier provide to a domestic customer based on meter readings?"
TEMPORAL_GROUPS = [
    {
        "heading": "Was this protection in force yet?",
        "sub": "a rule that was introduced later - RIA says whether it existed then and when it came in",
        "examples": [
            ("Credit balances · 2021", _CCB_Q, date(2021, 6, 1)),  # before 4D (introduced 20 Sep 2023)
            ("Credit balances · 2024", _CCB_Q, date(2024, 6, 1)),  # after
            ("EBSS 2022", _EBSS_Q, date(2022, 1, 1)),              # before 25E (introduced 24 Sep 2022)
            ("EBSS 2023", _EBSS_Q, date(2023, 6, 1)),              # after
        ],
    },
    {
        "heading": "Same rule, stronger protections over time",
        "sub": "a new obligation was added - RIA serves the version in force on the date",
        "examples": [
            ("Prepayment · 2021", _PPM_Q, date(2021, 6, 1)),  # before Cond 28 text change (8 Nov 2023)
            ("Prepayment · 2024", _PPM_Q, date(2024, 6, 1)),  # after - involuntary-PPM protections
            ("Meter billing · 2020", _BMR_Q, date(2020, 6, 1)),  # before Cond 21B 21B.5A (31 Dec 2020)
            ("Meter billing · 2022", _BMR_Q, date(2022, 6, 1)),  # after - smart-meter monthly billing info
        ],
    },
    {
        "heading": "Same rule, wider coverage over time",
        "sub": "who it protects was broadened - RIA serves the version in force on the date",
        "examples": [
            ("Business fairness · 2023", _NDF_Q, date(2023, 6, 1)),  # before 0A change (1 Jul 2024): microbusiness only
            ("Business fairness · 2025", _NDF_Q, date(2025, 1, 1)),  # after - all non-domestic customers
        ],
    },
]

# Conditions whose version history is mapped (text-change + introduced) — generated from the
# temporal module so the coverage line below stays accurate as more conditions are mapped.
def _cond_sort_key(c: str):
    num = ""
    for ch in c:
        if ch.isdigit():
            num += ch
        else:
            break
    return (int(num) if num else 999, c)


MAPPED_CONDS_STR = ", ".join(
    sorted(set(temporal.TEXT_CHANGES) | set(temporal.MAPPED), key=_cond_sort_key)
)

st.set_page_config(page_title="Regulatory Intelligence Assistant (RIA)", page_icon="⚡", layout="centered")

# Make the Anthropic key available whether it's in a local .env (dev - handled by
# rag.py's load_dotenv) or in Streamlit Cloud secrets (deploy). Belt-and-braces so the
# SDK finds ANTHROPIC_API_KEY regardless of how the platform exposes secrets.
try:
    if not os.getenv("ANTHROPIC_API_KEY") and "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:  # noqa: BLE001 - no secrets.toml locally is fine
    pass

# --- Brand theme to match scottdmarshall.com/ai-demo (Archivo font, orange headings) ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800;900&display=swap');
    html, body, .stApp, [data-testid="stAppViewContainer"],
    .stMarkdown, p, li, label, input, textarea, button, .stButton button {
        font-family: 'Archivo', sans-serif;
    }
    .stApp h1, .stApp h2, .stApp h3 {
        color: #FF6600;
        font-family: 'Archivo', sans-serif;
        font-weight: 800;
    }
    /* All buttons orange with white text */
    .stButton button, [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {
        background-color: #FF6600 !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 600;
    }
    .stButton button:hover, [data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-primary"]:hover {
        background-color: #E65C00 !important;   /* slightly darker on hover */
        color: #FFFFFF !important;
    }
    .stButton button:focus, .stButton button:active {
        background-color: #E65C00 !important;
        color: #FFFFFF !important;
        box-shadow: none !important;
    }
    /* Version-history "what changed" panel */
    .vh-card { border:1px solid #333; border-left:3px solid #FF6600; border-radius:8px;
               padding:12px 16px; margin:10px 0; background:rgba(255,102,0,0.05); }
    .vh-title { font-weight:800; color:#FF6600; margin-bottom:8px; font-size:1.02em; }
    .vh-timeline { font-size:0.9em; margin:4px 0; }
    .vh-sub { opacity:0.7; }
    .vh-line { color:#FF6600; opacity:0.75; }
    .vh-here { color:#FF6600; font-weight:700; }
    .vh-diff { font-size:0.9em; line-height:1.9; background:rgba(255,255,255,0.04);
               border-radius:6px; padding:10px 12px; margin-top:6px; }
    .vh-add { background:rgba(60,200,60,0.25); color:#9dff9d; border-radius:3px; padding:1px 4px; }
    .vh-del { color:#ff8a8a; text-decoration:line-through; opacity:0.8; }
    .vh-ctx { opacity:0.6; }
    .vh-gap { color:#FF6600; opacity:0.6; padding:0 4px; }
    /* Compare-two-dates side-by-side column */
    .cmp-col { max-height:460px; overflow-y:auto; padding:10px 12px; border:1px solid #333;
               border-radius:8px; background:rgba(255,255,255,0.03); font-size:0.85em; line-height:1.75; }

    /* Hide Streamlit chrome for a clean embed */
    #MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; height: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


_MD_ITALIC_LINE = re.compile(r"(?m)^_(.+)_$")   # footer lines: _**Please note:** x_
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)   # headings + inline emphasis
_MD_LINEBREAK = re.compile(r"[ \t]+\n")         # markdown's trailing-two-space hard breaks


def _plain_text(md: str) -> str:
    """Markdown -> plain text, for copying out.

    RIA's readers are non-technical and paste into Word / Outlook, which do NOT render Markdown -
    they would show literal `**asterisk soup**`. Stripping the markers costs only bold headings;
    the structure survives on line breaks alone, and the parts that matter for an audit trail (the
    per-block Source lines, the version/as-of footer, the scope disclaimer) travel intact.
    """
    t = md.replace("—", "-")            # match what the page displays
    t = _MD_ITALIC_LINE.sub(r"\1", t)   # unwrap italics BEFORE bold, so _**x:** y_ -> x: y
    t = _MD_BOLD.sub(r"\1", t)
    t = _MD_LINEBREAK.sub("\n", t)
    return t.strip()


def _copy_text(question: str, result: dict) -> str:
    """The copied artefact: self-contained and auditable. A pasted answer with no question is
    contextless to the colleague receiving it, and the as-of date is what makes a regulatory
    position meaningful - so both lead. (The footer repeats the as-of date as provenance; that is
    deliberate - context at the top, provenance at the bottom.)"""
    as_of = temporal.fmt(date.fromisoformat(result["as_of"]))
    return _plain_text(f"Question: {question}\nAs of: {as_of}\n\n{result['answer']}")


@st.cache_resource(show_spinner=False)
def _collection():
    return get_collection()


@st.cache_resource(show_spinner=False)
def _client():
    return get_client()


@st.cache_resource(show_spinner=False)
def _usage():
    # Shared across all sessions in this container; resets if the container restarts.
    return {"date": None, "count": 0}


def _reserve_daily_slot() -> bool:
    """Increment the shared daily counter; False if the daily cap is reached."""
    import datetime

    today = datetime.date.today().isoformat()
    u = _usage()
    if u["date"] != today:
        u["date"], u["count"] = today, 0
    if u["count"] >= MAX_PER_DAY:
        return False
    u["count"] += 1
    return True


def _san(t: str) -> str:
    """Escape HTML and flatten em-dashes for safe inline rendering."""
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("—", "-")


def _diff_html(segs: list[dict]) -> str:
    out = []
    for s in segs:
        if s["type"] == "add":
            out.append(f'<span class="vh-add">{_san(s["text"])}</span>')
        elif s["type"] == "del":
            out.append(f'<span class="vh-del">{_san(s["text"])}</span>')
        elif s["type"] == "gap":
            out.append('<span class="vh-gap"> … </span>')
        else:
            out.append(f'<span class="vh-ctx">{_san(s["text"])}</span>')
    return " ".join(out)


def _side_html(segs: list[dict]) -> str:
    """Render one column of a side-by-side compare: unchanged text plain, add green, del struck-red."""
    out = []
    for s in segs:
        t = _san(s["text"])
        if s["type"] == "del":
            out.append(f'<span class="vh-del">{t}</span>')
        elif s["type"] == "add":
            out.append(f'<span class="vh-add">{t}</span>')
        else:
            out.append(t)
    return f'<div class="cmp-col">{" ".join(out)}</div>'


def render_history(h: dict) -> None:
    """Render the 'what changed' panel for one mapped condition."""
    title = (f'<div class="vh-title">📜 Version history — Condition {h["condition"]} · '
             f'{_san(h["title"])}</div>')
    if h["kind"] == "text-change":
        marks = " <span class='vh-line'>──→</span> ".join(
            f'● <b>{m["date"]}</b> <span class="vh-sub">({m["label"]})</span>' for m in h["markers"]
        )
        timeline = f'<div class="vh-timeline">{marks} <span class="vh-line">──→ today</span></div>'
        showing = h["markers"][-1]["date"] if h["on_after"] else h["markers"][0]["date"]
        side = "on/after" if h["on_after"] else "before"
        here = (f'<div class="vh-sub" style="margin:4px 0 8px">You asked <b>as of {h["as_of"]}</b> - '
                f'<span class="vh-here">{side}</span> the {h["change_date"]} change, so RIA shows the '
                f'<b>{showing}</b> text.</div>')
        more = ' <span class="vh-gap">…(+more)</span>' if h["diff_truncated"] else ''
        diff = (f'<div class="vh-sub"><b>What changed on {h["change_date"]}:</b> '
                f'<span class="vh-add">added</span> · <span class="vh-del">removed</span></div>'
                f'<div class="vh-diff">{_diff_html(h["diff"])}{more}</div>')
        body = title + timeline + here + diff
    else:  # introduced
        marks = (f'<span class="vh-sub">did not exist</span> <span class="vh-line">──→</span> '
                 f'● <b>{h["introduced"]}</b> <span class="vh-sub">(introduced)</span> '
                 f'<span class="vh-line">──→ today</span>')
        state = "existed" if h["existed"] else "did <b>not</b> exist yet"
        body = (title + f'<div class="vh-timeline">{marks}</div>'
                f'<div class="vh-sub" style="margin-top:6px">As of <b>{h["as_of"]}</b>, this '
                f'condition {state} - introduced <b>{h["introduced"]}</b>.</div>')
    st.markdown(f'<div class="vh-card">{body}</div>', unsafe_allow_html=True)


def render_compare(condition: str) -> None:
    """Full before/after side-by-side for a text-change condition — a drill-down under its
    version-history card, so it always shows the condition the user asked about."""
    cmp = history.compare(condition)
    if not cmp:
        return
    with st.expander(f"🔀 Compare the full text side by side — before vs after {cmp['change_date']}"):
        lcol, rcol = st.columns(2)
        with lcol:
            st.markdown(f"**◀ Before** · in force {cmp['left']['in_force']}  \n"
                        f"_{cmp['left']['consolidation']} consolidation_")
            st.markdown(_side_html(cmp["left"]["segs"]), unsafe_allow_html=True)
        with rcol:
            st.markdown(f"**After ▶** · in force {cmp['right']['in_force']}  \n"
                        f"_{cmp['right']['consolidation']} consolidation_")
            st.markdown(_side_html(cmp["right"]["segs"]), unsafe_allow_html=True)
        st.caption("Green = added in the newer version · struck-through red = removed.")


# --- Header ---
st.title("⚡ Regulatory Intelligence Assistant (RIA)")
st.caption(
    "**RIA** is a proof-of-concept, scoped to **Ofgem electricity supply licence "
    "conditions** and grounded in the current consolidated version "
    f"({temporal.current_version_str()}). "
    "She can also answer **as of a past date** - pick a date and ask, and she'll tell you "
    "whether a given protection was in force then, when it was introduced, and how its wording "
    "has changed - with historic coverage expanding condition by condition. Unlike a generic AI, "
    "RIA answers only from "
    "the licence text: when the answer isn't there, or she can't verify the position on a "
    "past date, she says so plainly rather than inventing (hallucinating) one - and every "
    "answer is backed by specific citations. _Informational only - not legal advice._"
)

# --- Store present? ---
if not STORE.exists():
    st.error(
        "Vector store not found. Run the ingestion pipeline first:\n\n"
        "`venv/bin/python src/extract_pages.py` → `src/chunk.py` → `src/embed.py`"
    )
    st.stop()

if "question" not in st.session_state:
    st.session_state.question = ""
if "as_of" not in st.session_state:
    st.session_state.as_of = date.today()

# --- Example questions ---
st.write("**Try an example:**")
PER_ROW = 3
for start in range(0, len(EXAMPLES), PER_ROW):
    cols = st.columns(PER_ROW)  # fixed width so labels wrap only at spaces
    for col, (label, q) in zip(cols, EXAMPLES[start : start + PER_ROW]):
        if col.button(label, help=q, use_container_width=True):
            st.session_state.question = q
            st.session_state.as_of = date.today()  # current-position examples

st.write("**Broad questions** - open “what are all our duties around …?” questions. "
         "RIA plans focused sub-searches and answers **grouped by obligation**, surfacing every "
         "relevant condition rather than only the closest match. "
         f"Every question is searched against all {condition_count(_collection())} conditions of "
         "the electricity supply licence:")
for start in range(0, len(BROAD_EXAMPLES), PER_ROW):
    cols = st.columns(PER_ROW)
    for col, (label, q) in zip(cols, BROAD_EXAMPLES[start : start + PER_ROW]):
        if col.button(label, help=q, use_container_width=True):
            st.session_state.question = q
            st.session_state.as_of = date.today()  # current-position examples

st.write("**…or ask a historic “as of date” question - the same question answered at different dates. "
         "RIA handles three kinds of change:**")
T_PER_ROW = 2  # each row = one condition's before/after
for group in TEMPORAL_GROUPS:
    st.markdown(f"**{group['heading']}**  \n_{group['sub']}_")
    for start in range(0, len(group["examples"]), T_PER_ROW):
        tcols = st.columns(T_PER_ROW)
        for col, (label, q, d) in zip(tcols, group["examples"][start : start + T_PER_ROW]):
            if col.button(label, help=f"{q}  -  as of {d.strftime('%d %b %Y').lstrip('0')}", use_container_width=True):
                st.session_state.question = q
                st.session_state.as_of = d  # sets both question and the date picker

# --- Question input ---
question = st.text_input(
    "Your question", key="question", max_chars=MAX_QUESTION_CHARS,
    placeholder="e.g. When can a supplier disconnect a domestic customer?",
)
as_of = st.date_input(
    "⏳ As of date", key="as_of", max_value=date.today(),
    help="Ask what the rules were as of a past date. Leave at today for the current position.",
)
ask = st.button("Ask RIA", type="primary")

if ask and question.strip():
    # Per-session cap (Layer 1)
    if st.session_state.get("asked", 0) >= MAX_PER_SESSION:
        st.warning(
            f"You've reached this demo's limit of {MAX_PER_SESSION} questions per session. "
            "Refresh the page to start a new session, or get in touch with Scott to discuss."
        )
        st.stop()
    # Global soft daily cap (Layer 3)
    if not _reserve_daily_slot():
        st.info("This demo has reached its daily question limit. Please try again tomorrow.")
        st.stop()
    st.session_state.asked = st.session_state.get("asked", 0) + 1

    try:
        with st.spinner("Retrieving relevant conditions and reading them…"):
            result = answer_question(question, coll=_collection(), client=_client(), as_of=as_of)
    except Exception as e:  # noqa: BLE001 - surface a friendly message, not a stack trace
        msg = str(e)
        if "api_key" in msg.lower() or "authentication" in msg.lower():
            st.error("Anthropic API key missing or invalid. Check your `.env` file.")
        else:
            st.error(f"Something went wrong calling the model:\n\n{msg}")
        st.stop()

    st.divider()

    if as_of != date.today():
        st.info(f"🕰️ Answering **as of {as_of.strftime('%d %B %Y').lstrip('0')}** - a historic date.")

    # --- Answer or refusal ---
    if result["refused"]:
        st.warning("**Not in the source material.**")
        st.write(result["reason"].replace("—", "-"))
    else:
        # The answer now carries a one-line headline, plain-language obligation blocks, and per-block
        # "Source: Condition X" lines (with deterministic version/effective dates) — so the separate
        # Citations list is redundant. Full titles + pages remain in the retrieved-sources expander.
        st.markdown(result["answer"].replace("—", "-"))

        # Copy-out. st.code() carries Streamlit's own copy icon, so this needs no JS and cannot
        # silently fail the way a clipboard call from Streamlit's sandboxed iframe can. Collapsed
        # by default: it is furniture for the people who want it, invisible to everyone else.
        # The label must describe what opening this REVEALS, not an action it performs. Labelling it
        # "Copy question and answer" promised a copy, delivered a box, and read as broken software -
        # the copy icon inside is the only control that should promise copying.
        with st.expander("📋 Plain-text version (question + answer) - to copy"):
            # The instruction goes ABOVE the box: below it, on a long broad answer, the reader has
            # scrolled past the icon before they learn it exists.
            st.caption("Hover over the box below and click the copy icon in its **top-right corner** "
                       "to copy everything. It pastes as plain text into Word, Outlook or an email.")
            # height= is load-bearing, NOT cosmetic. The default ("content") grows the box to the full
            # length of the answer, and the copy icon sits at the top-right OF THE BLOCK - so on a long
            # broad answer it scrolls out of view and reads as "the icon disappeared". A fixed height
            # makes the box scroll internally and keeps its toolbar in reach.
            st.code(_copy_text(question, result), language=None, wrap_lines=True, height=260)

    # --- Version history "what changed" panel (mapped conditions in the answer) ---
    # Defensive: this panel is a supplementary enhancement — the answer + citations are already
    # shown above. If a half-updated deploy leaves these render helpers out of sync (e.g. a stale
    # `history` module missing `compare()`), degrade gracefully: skip the panel, log to the server
    # logs, and never crash the whole answer. Guarded per-entry so one bad entry can't sink the rest.
    for h in result.get("history", []):
        try:
            render_history(h)
            if h["kind"] == "text-change":
                render_compare(h["condition"])  # full side-by-side, always for the asked condition
        except Exception as e:  # noqa: BLE001 — supplementary UI must never break the answer
            print(f"[version-history panel skipped] {type(e).__name__}: {e}", flush=True)
    if result.get("history"):
        st.caption(
            f"Version history is mapped so far for Conditions {MAPPED_CONDS_STR} - coverage is "
            "expanding condition by condition. Other conditions in this answer don't yet have a "
            "version comparison."
        )

    # --- Retrieved sources (transparency; removable later) ---
    with st.expander(f"🔎 Retrieved sources (top {TOP_K}, hybrid rank)"):
        st.caption("Hybrid retrieval (semantic + keyword). Number = vector distance "
                   "(lower is closer); `kw` = surfaced by the keyword match. PoC transparency.")
        for m in result["retrieved"]:
            dist = m["distance"] if m["distance"] is not None else "kw"
            st.markdown(
                f"`{dist}`  **Condition {m['condition']}** - {m['condition_title']} "
                f"(pp. {m['pages']})"
            )

    st.caption(f"Question {st.session_state.asked} of {MAX_PER_SESSION} this session.")
elif ask:
    st.info("Type a question first, or pick an example above.")
