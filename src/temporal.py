"""
Phase 6 — Temporal / version awareness.

Holds the change history for the conditions we have VERIFIED, and turns an
"as of date" + the conditions surfaced by retrieval into plain facts the model
can reason over. Two kinds of mapped condition:

  * EXISTENCE-BOUNDARY (MAPPED) — a cleanly-introduced condition: it either existed
    as of a date, or it did not (25E, 4D). No historic body to serve; we just state
    non-existence before its introduction.
  * TEXT-CHANGE (TEXT_CHANGES) — a condition whose TEXT changed on a known date, with
    a held consolidation on each side (28 — Prepayment Meters, changed 8 Nov 2023).
    We serve the version of the text that was in force as of the date.

Adding a condition later = one more entry here (+ its verified history).
"""
from __future__ import annotations

from datetime import date

try:  # works both as `src.temporal` (app/evals) and `import temporal` (python src/*)
    from src import versions
except ImportError:
    import versions

# --- Existence-boundary conditions. `introduced` = the date it came into the licence. ---
MAPPED: dict[str, dict] = {
    "25E": {
        "title": "Power to direct Energy Bill Support Scheme Payments",
        "introduced": date(2022, 9, 24),   # EBSS supplier licence decision notice
    },
    "4D": {
        "title": "Protecting Domestic Customer Credit Balances",
        "introduced": date(2023, 9, 20),   # Decision OFG1163 (26 Jul 2023) + 56 days
    },
}

# --- Text-change conditions. Segments are contiguous and gap-free by construction:
# each [start, end) interval maps to the held version whose text applied then. ---
TEXT_CHANGES: dict[str, dict] = {
    "21B": {
        "title": "Billing based on meter readings",
        # Verified single change: paragraph 21B.5A inserted, effective 31 Dec 2020 (SI 2020/1401,
        # Clean Energy Package transposition). Text then identical v2022 == v2025. The BEFORE side
        # lives in v2019 - the first mapping to use the 2019 consolidation.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2020, 12, 31),
                "version": "2019-08-03",
                "note": ("before paragraph 21B.5A was inserted - suppliers were not yet required to "
                         "offer smart-meter (remote-reading) domestic customers monthly billing "
                         "information based on actual consumption"),
            },
            {
                "start": date(2020, 12, 31),
                "end": None,  # open - current (text unchanged from v2022 through v2025)
                "version": "2025-08-01",
                "note": ("paragraph 21B.5A added (effective 31 December 2020, Clean Energy Package / "
                         "Electricity Directive transposition): where a domestic customer has a meter "
                         "with remote-reading enabled (a smart meter), the supplier must offer to "
                         "provide monthly billing information based on actual consumption"),
            },
        ],
    },
    "0A": {
        "title": "Treating Non-Domestic Customers Fairly",
        # Verified unchanged 2019-08-03 -> 2022-04-14 (detector I1 sim 1.0); single change
        # effective 1 Jul 2024 (Non-Domestic Market Review). Earlier is outside our knowledge.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2024, 7, 1),
                "version": "2022-04-14",
                "note": ("applied only to Micro Business Consumers — the condition was then "
                         "titled 'Treating Microbusiness Consumers Fairly'"),
            },
            {
                "start": date(2024, 7, 1),
                "end": None,  # open — current
                "version": "2025-08-01",
                "note": ("expanded by the Non-Domestic Market Review (effective 1 July 2024) so "
                         "the Standards of Conduct apply to ALL Non-Domestic Customers, not just "
                         "microbusinesses; every 'Micro Business Consumer' reference became "
                         "'Non-Domestic Customer'"),
            },
        ],
    },
    "28": {
        "title": "Prepayment Meters",
        # Earliest date we can vouch for the text. Verified unchanged 2019-08-03 -> 2022-04-14
        # (so the v2022 snapshot's text is correct back to the 2019 consolidation); before
        # that is outside our knowledge.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2023, 11, 8),
                "version": "2022-04-14",
                "note": ("the shorter pre-reform text; the involuntary-prepayment-meter Code of "
                         "Practice had not yet been written into the licence"),
            },
            {
                "start": date(2023, 11, 8),
                "end": None,  # open — current
                "version": "2025-08-01",
                "note": ("expanded to incorporate the involuntary-prepayment-meter Code of Practice "
                         "(effective 8 November 2023): vulnerability assessment, proportionality, and "
                         "further protections before a prepayment meter is installed involuntarily"),
            },
        ],
    },
}


def fmt(d: date) -> str:
    """'24 September 2022' (no leading zero on the day)."""
    return d.strftime("%d %B %Y").lstrip("0")


# CURRENT (latest held) version — derived from the registry so there is no hardcoded
# "current date" anywhere in the serving path. Ingest a newer consolidation → it becomes
# current automatically (see src/versions.py).
CURRENT_VERSION_DATE = versions.CURRENT_DATE


def current_version_str() -> str:
    return fmt(CURRENT_VERSION_DATE)  # e.g. "1 August 2025"


def existed(condition: str, as_of: date) -> bool | None:
    """True/False if the condition is an existence-boundary mapped one, else None."""
    m = MAPPED.get(condition)
    if m is None:
        return None
    return as_of >= m["introduced"]


def _segment(condition: str, as_of: date):
    """For a text-change condition: the segment in force at `as_of`, the string
    'TOO_EARLY' if before our earliest held text, or None if not text-mapped."""
    tc = TEXT_CHANGES.get(condition)
    if tc is None:
        return None
    if as_of < tc["earliest"]:
        return "TOO_EARLY"
    for seg in tc["segments"]:
        if as_of >= seg["start"] and (seg["end"] is None or as_of < seg["end"]):
            return seg
    return None


def version_for(condition: str, as_of: date) -> str | None:
    """The version label whose text should be SERVED for `condition` as of `as_of`.
    CURRENT for anything not text-mapped (or resolving to the current segment); the
    held historic label for a past segment; None if before our earliest knowledge
    (caller should caveat / not assert content)."""
    seg = _segment(condition, as_of)
    if seg is None:
        return versions.CURRENT_LABEL
    if seg == "TOO_EARLY":
        return None
    return seg["version"]


def scope_note(as_of: date) -> str | None:
    """For a PAST date, state which conditions have verified history and require the model
    to caveat all others (so current text is never passed off as the historic position)."""
    if as_of >= date.today():
        return None
    covered = ", ".join(f"Condition {c}" for c in sorted(set(MAPPED) | set(TEXT_CHANGES)))
    return (
        f"IMPORTANT (historic query, as of {fmt(as_of)}): verified historical coverage exists "
        f"ONLY for {covered}. For ANY other condition, you have only its CURRENT "
        f"({current_version_str()}) text — you must NOT present that as the position as of "
        f"{fmt(as_of)}. State plainly that "
        f"you can only show the current text and cannot confirm whether it applied unchanged on "
        f"that date (the condition may have been modified since)."
    )


def temporal_notes(conditions: set[str], as_of: date) -> list[str]:
    """Plain facts for each EXISTENCE-BOUNDARY mapped condition among the retrieved ones."""
    notes = []
    for c in sorted(conditions):
        m = MAPPED.get(c)
        if m is None:
            continue
        state = (
            "was in force (its current text applies)"
            if as_of >= m["introduced"]
            else "did NOT yet exist in the licence"
        )
        notes.append(
            f"Condition {c} ({m['title']}) was introduced on {fmt(m['introduced'])}. "
            f"As of {fmt(as_of)}, it {state}."
        )
    return notes


def text_change_notes(conditions: set[str], as_of: date) -> list[str]:
    """Plain facts for each TEXT-CHANGE mapped condition among the retrieved ones: which
    version's text is in force as of the date, its effective range, and the change date(s)
    (so the model can surface both states if the question's period straddles a change)."""
    notes = []
    for c in sorted(conditions):
        tc = TEXT_CHANGES.get(c)
        if tc is None:
            continue
        change_dates = ", ".join(fmt(s["start"]) for s in tc["segments"][1:])
        seg = _segment(c, as_of)
        if seg == "TOO_EARLY":
            notes.append(
                f"Condition {c} ({tc['title']}): its text changed on {change_dates}, but our "
                f"earliest held text is {fmt(tc['earliest'])}. As of {fmt(as_of)} (earlier) the "
                f"historic text is NOT held — do not assert its content; say it cannot be confirmed."
            )
            continue
        v = versions.BY_LABEL[seg["version"]]
        rng = f"from {fmt(seg['start'])}" + (f" until {fmt(seg['end'])}" if seg["end"] else " to now")
        notes.append(
            f"Condition {c} ({tc['title']}) had its TEXT changed on {change_dates}. As of "
            f"{fmt(as_of)}, the text in force is that of the consolidation {fmt(v['date'])} "
            f"({rng}): {seg['note']}. The retrieved extract for Condition {c} is that version's "
            f"text — answer from it, and state the effective version/date ({fmt(v['date'])})."
        )
    return notes
