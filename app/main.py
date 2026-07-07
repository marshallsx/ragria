"""
Phase 4 — Streamlit UI.

Single-turn Q&A over the Ofgem Electricity Supply Standard Licence Conditions,
wired to src.rag.answer_question(). Shows the grounded answer, condition-level
citations, a clear "not in source material" refusal state, and a collapsible
panel of the retrieved sources (transparency during the PoC).

Run: streamlit run app/main.py
"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rag import STORE, TOP_K, answer_question, get_client, get_collection  # noqa: E402

EXAMPLES = [
    ("Back-billing limit", "Can a supplier back-bill a domestic customer for consumption more than 12 months ago?"),
    ("Disconnection for debt", "What must we do before disconnecting a domestic customer for debt?"),
    ("Priority Services Register", "What are our Priority Services Register obligations for identifying and recording vulnerable customers?"),
    ("Blocking a switch", "Can a supplier block a customer from switching to another supplier?"),
    ("Security deposits", "What are the rules on security deposits for domestic customers?"),
    ("Out of scope ↩", "What safety certifications are required to install a domestic gas boiler?"),
]

st.set_page_config(page_title="Regulatory Intelligence Assistant (RIA)", page_icon="⚡", layout="centered")


@st.cache_resource(show_spinner=False)
def _collection():
    return get_collection()


@st.cache_resource(show_spinner=False)
def _client():
    return get_client()


# --- Header ---
st.title("⚡ Regulatory Intelligence Assistant (RIA)")
st.caption(
    "Grounded in **public Ofgem Electricity Supply Standard Licence Conditions**, "
    "consolidated to 1 August 2025. Answers come only from the source text, with "
    "citations — and the assistant refuses when the answer isn't there. "
    "_Informational only — not legal advice._"
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

# --- Example questions ---
st.write("**Try an example:**")
PER_ROW = 3
for start in range(0, len(EXAMPLES), PER_ROW):
    cols = st.columns(PER_ROW)  # fixed width so labels wrap only at spaces
    for col, (label, q) in zip(cols, EXAMPLES[start : start + PER_ROW]):
        if col.button(label, help=q, use_container_width=True):
            st.session_state.question = q

# --- Question input ---
question = st.text_input("Your question", key="question", placeholder="e.g. When can a supplier disconnect a domestic customer?")
ask = st.button("Ask", type="primary")

if ask and question.strip():
    try:
        with st.spinner("Retrieving relevant conditions and reading them…"):
            result = answer_question(question, coll=_collection(), client=_client())
    except Exception as e:  # noqa: BLE001 — surface a friendly message, not a stack trace
        msg = str(e)
        if "api_key" in msg.lower() or "authentication" in msg.lower():
            st.error("Anthropic API key missing or invalid. Check your `.env` file.")
        else:
            st.error(f"Something went wrong calling the model:\n\n{msg}")
        st.stop()

    st.divider()

    # --- Answer or refusal ---
    if result["refused"]:
        st.warning("**Not in the source material.**")
        st.write(result["reason"])
    else:
        st.markdown(result["answer"])
        if result["citations"]:
            st.subheader("Citations")
            for c in result["citations"]:
                st.markdown(f"- **Condition {c['condition']}** — {c['condition_title']} (pp. {c['pages']})")

    # --- Retrieved sources (transparency; removable later) ---
    with st.expander(f"🔎 Retrieved sources (top {TOP_K}, hybrid rank)"):
        st.caption("Hybrid retrieval (semantic + keyword). Number = vector distance "
                   "(lower is closer); `kw` = surfaced by the keyword match. PoC transparency.")
        for m in result["retrieved"]:
            dist = m["distance"] if m["distance"] is not None else "kw"
            st.markdown(
                f"`{dist}`  **Condition {m['condition']}** — {m['condition_title']} "
                f"(pp. {m['pages']})"
            )
elif ask:
    st.info("Type a question first, or pick an example above.")
