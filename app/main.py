"""
Phase 4 - Streamlit UI.

Single-turn Q&A over the Ofgem Electricity Supply Standard Licence Conditions,
wired to src.rag.answer_question(). Shows the grounded answer, condition-level
citations, a clear "not in source material" refusal state, and a collapsible
panel of the retrieved sources (transparency during the PoC).

Run: streamlit run app/main.py
"""
import os
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import temporal  # noqa: E402
from src.rag import STORE, TOP_K, answer_question, get_client, get_collection  # noqa: E402

# --- Public-demo safeguards ---
MAX_PER_SESSION = 10       # questions per browser session
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

# Temporal examples set the question AND a past "as of" date to showcase the time travel.
# The same credit-balances question at 2021 vs 2024 is the striking before/after.
_CCB_Q = "Do suppliers have to protect domestic customer credit balances?"
_EBSS_Q = "Can the Secretary of State direct suppliers to make Energy Bill Support Scheme payments?"
TEMPORAL_EXAMPLES = [
    ("Credit balances · 2021", _CCB_Q, date(2021, 6, 1)),      # before 4D (introduced 20 Sep 2023)
    ("Credit balances · 2024", _CCB_Q, date(2024, 6, 1)),      # after
    ("EBSS 2022", _EBSS_Q, date(2022, 1, 1)),  # before 25E (introduced 24 Sep 2022)
    ("EBSS 2023", _EBSS_Q, date(2023, 6, 1)),  # after
]

st.set_page_config(page_title="Regulatory Intelligence Trusted Assistant (RITA)", page_icon="⚡", layout="centered")

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
    /* Hide Streamlit chrome for a clean embed */
    #MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; height: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


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


# --- Header ---
st.title("⚡ Regulatory Intelligence Trusted Assistant (RITA)")
st.caption(
    "**RITA** is a proof-of-concept, scoped to **Ofgem electricity supply licence "
    "conditions** and grounded in the current consolidated version "
    f"({temporal.current_version_str()}). "
    "She can also answer **as of a past date** - pick a date and ask, and she'll tell you "
    "whether a given protection was in force then and when it was introduced - with historic "
    "coverage expanding condition by condition. Unlike a generic AI, RITA answers only from "
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

st.write("**…or a historic “as of date” question - same question, before vs after it existed:**")
T_PER_ROW = 2  # each row = one condition's before/after
for start in range(0, len(TEMPORAL_EXAMPLES), T_PER_ROW):
    tcols = st.columns(T_PER_ROW)
    for col, (label, q, d) in zip(tcols, TEMPORAL_EXAMPLES[start : start + T_PER_ROW]):
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
ask = st.button("Ask RITA", type="primary")

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
        st.markdown(result["answer"].replace("—", "-"))
        if result["citations"]:
            st.subheader("Citations")
            for c in result["citations"]:
                st.markdown(f"- **Condition {c['condition']}** - {c['condition_title']} (pp. {c['pages']})")

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
