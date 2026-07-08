"""
Phase 6 — Temporal / version awareness (existence-boundary increment).

Holds the change timeline for the conditions we have VERIFIED, and turns an
"as of date" + the conditions surfaced by retrieval into plain facts the model
can reason over. Scoped, for this increment, to two cleanly-introduced conditions
(existence boundary): a condition either existed as of a date, or it did not.

Adding a condition later = one more entry here (+ its verified history).
"""
from __future__ import annotations

from datetime import date

# Verified mapped conditions. `introduced` = the date the condition came into the
# electricity supply licence (from Ofgem's modification notices).
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


def fmt(d: date) -> str:
    """'24 September 2022' (no leading zero on the day)."""
    return d.strftime("%d %B %Y").lstrip("0")


def existed(condition: str, as_of: date) -> bool | None:
    """True/False if the condition is mapped, else None (unmapped → unknown)."""
    m = MAPPED.get(condition)
    if m is None:
        return None
    return as_of >= m["introduced"]


def temporal_notes(conditions: set[str], as_of: date) -> list[str]:
    """Plain facts for each mapped condition among the retrieved ones, given the date."""
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
