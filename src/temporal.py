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
    # Supplier Licensing Review "ongoing requirements" — both introduced 18 Mar 2021 (Scott-verified).
    # Verified absent in v2019, present + text-stable v2022==v2025 (sim 1.00), so pure existence
    # boundary: no historic body to serve, we just state non-existence before the introduction date.
    "4C": {
        "title": "Ongoing fit and proper requirement",
        "introduced": date(2021, 3, 18),
    },
    "19C": {
        "title": "Customer supply continuity plans",
        "introduced": date(2021, 3, 18),
    },
    # Supplier Licensing Review governance conditions — all introduced 22 Jan 2021 (Scott-verified,
    # Ofgem). Verified absent in v2019, present + text-stable across v2022 → v2025 (pure existence
    # boundaries: no historic body to serve, we just state non-existence before the introduction date).
    "5A": {
        "title": "Principle to be open and cooperative",  # corpus title has a typo ("Priniciple")
        "introduced": date(2021, 1, 22),
    },
    "5B": {
        "title": "Independent Audits",
        "introduced": date(2021, 1, 22),
    },
    "19D": {
        "title": "Trade Sales",
        "introduced": date(2021, 1, 22),
    },
    # Elexon ownership — introduced 1 Oct 2024 (decision 13 Sep 2024, Scott-verified). Absent through
    # v2024-07, present from v2024-10; the SECOND mapping to rely on a 2024 consolidation, and the
    # first whose existence boundary falls between the two 2024 snapshots.
    "60": {
        "title": "Elexon ownership",
        "introduced": date(2024, 10, 1),
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
    "27A": {
        "title": "Self-disconnection",
        # INTRODUCED 15 Dec 2020 (Ofgem self-disconnection / self-rationing prepayment decision) —
        # verified absent in v2019, present from v2022 (Scott-confirmed effective date). Before this
        # date it did NOT exist, so a pre-introduction query asserts NON-EXISTENCE (existence
        # boundary), not the "text not held" caveat. Then a SINGLE text change effective 8 Nov 2023
        # (the involuntary-prepayment-meter Code of Practice — the SAME reform that changed Condition
        # 28): paragraphs 27A.7A-27A.7C (Involuntary Prepayment Meter Credit) were inserted, nothing
        # removed. Text verified stable from introduction through the v2022 consolidation. Gap-free:
        # v2022 holds the pre-IPPM text, v2025 the post-IPPM text.
        "introduced": date(2020, 12, 15),   # existence boundary: before this it did NOT exist
        "earliest": date(2020, 12, 15),
        "segments": [
            {
                "start": date(2020, 12, 15),
                "end": date(2023, 11, 8),
                "version": "2022-04-14",
                "note": ("the pre-involuntary-PPM text: identifying self-disconnection and offering "
                         "support, Emergency Credit and Friendly-hours Credit — but NOT the "
                         "Involuntary Prepayment Meter Credit paragraphs (27A.7A-27A.7C) added later"),
            },
            {
                "start": date(2023, 11, 8),
                "end": None,  # open — current
                "version": "2025-08-01",
                "note": ("expanded by the involuntary-prepayment-meter Code of Practice (effective "
                         "8 November 2023, the same reform as Condition 28): paragraphs 27A.7A-27A.7C "
                         "added, requiring Involuntary Prepayment Meter Credit on each occasion an "
                         "involuntary prepayment meter is installed under SLC 28.7"),
            },
        ],
    },
    "31H": {
        "title": "Relevant Billing Information, Bills and statements of account",
        # Verified single change effective 31 Dec 2020 (Clean Energy Package / recast Electricity
        # Directive transposition into domestic law — the SAME date as 21B): bills must show a price
        # breakdown corresponding to the three main components, plus added payment-timing information
        # and recast-Directive references. BEFORE side = v2019; text then stable v2022 == v2025
        # (sim 1.00). NOTE: an earlier 11 Feb 2019 change predates our earliest held consolidation
        # (already baked into v2019) so it is not demonstrable and is NOT mapped. Gap-free.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2020, 12, 31),
                "version": "2019-08-03",
                "note": ("the pre-Clean-Energy-Package billing text: without the requirement to show a "
                         "price breakdown corresponding to the three main components, and without the "
                         "added payment-timing information"),
            },
            {
                "start": date(2020, 12, 31),
                "end": None,  # open — current (text unchanged from v2022 through v2025)
                "version": "2025-08-01",
                "note": ("expanded by the Clean Energy Package / recast Electricity Directive "
                         "transposition (effective 31 December 2020, the same change as Condition 21B): "
                         "bills must show a price breakdown corresponding to the three main components "
                         "and set out when and how the customer must make payments"),
            },
        ],
    },
    "28": {
        "title": "Prepayment Meters",
        # Condition 28 dates back to the inaugural standard conditions of 1 Oct 2001, so it is not
        # an introduced condition. `earliest` is not when it began - it is the limit of what we can
        # EVIDENCE: 3 Aug 2019 is our oldest held consolidation, and dated queries before it refuse.
        #
        # CORRECTION (was a real defect): this previously ran ONE segment from 2019-08-03 to
        # 2023-11-08 on the v2022 text, commented "verified unchanged 2019-08-03 -> 2022-04-14".
        # That was false. Paragraph (bb) (Emergency Credit, Friendly-hours Credit and Additional
        # Support Credit "as defined in SLC 27A") was INSERTED effective 15 Dec 2020, so the old
        # first segment spanned two different texts and served 2019-2020 queries a paragraph
        # citing SLC 27A - a condition that did not exist on those dates. The similarity-threshold
        # change detector scored the edit 0.973 and reported it as unchanged; see c55ea2d.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2020, 12, 15),
                "version": "2019-08-03",
                "note": ("before the Ability to Pay / self-disconnection package: Condition 28 did "
                         "not yet require suppliers to explain Emergency Credit, Friendly-hours "
                         "Credit and Additional Support Credit, because SLC 27A - which defines "
                         "them - did not exist yet"),
            },
            {
                "start": date(2020, 12, 15),
                "end": date(2023, 11, 8),
                "version": "2022-04-14",
                "note": ("the pre-reform text as amended by the 15 December 2020 package "
                         "(paragraph (bb) added, cross-referring to the new SLC 27A); the "
                         "involuntary-prepayment-meter Code of Practice had not yet been written "
                         "into the licence"),
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
    "31G": {
        "title": "Assistance and advice information",
        # 31G was introduced 11 Feb 2019 (created 17 Dec 2018), before our earliest held consolidation
        # and text-stable 2019-08-03 == 2022-04-14 — so it is NOT an introduced condition here;
        # `earliest` is the knowledge boundary (dated queries before 3 Aug 2019 refuse).
        #
        # TWO Scott-verified single changes, each bracketed by held consolidations — the FIRST mapping
        # to use the 2024 consolidations (v2024-07):
        #  1. 14 Dec 2023 (Consumer Standards decision 18 Oct 2023, in force 14 Dec 2023): the whole
        #     31G.3A "Contact Ease" enquiry-service framework was added, INCLUDING 31G.3A(c) inserted
        #     as a DORMANT rule (its own caveat said it would only take effect after further Notice).
        #     Verified single change in the 2022-04-14 → 2024-07-01 window (Scott, Ofgem mod history).
        #  2. 1 Aug 2025 (24/7 Metering Support decision Apr 2025): 31G.3A(c) ACTIVATED — the dormancy
        #     caveat sentence was DELETED, making the 24-hour enquiry-service duty live. Verified the
        #     only change in the 2024-10-01 → 2025-08-01 window.
        # Gap-free: v2019 holds the pre-2023 text, v2024-07 the dormant-3A(c) text (stable through
        # v2024-10), v2025 the activated text.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2023, 12, 14),
                "version": "2019-08-03",
                "note": ("before the Consumer Standards reforms: the enquiry-service / 'Contact Ease' "
                         "framework of 31G.3A had not yet been added — suppliers were not yet required "
                         "to offer a range of contact methods meeting customers' needs"),
            },
            {
                "start": date(2023, 12, 14),
                "end": date(2025, 8, 1),
                "version": "2024-07-01",
                "note": ("31G.3A 'Contact Ease' enquiry-service framework added (Consumer Standards, "
                         "effective 14 December 2023): a range of contact methods and adequate hours "
                         "meeting customers' needs. The 24-hour requirement (31G.3A(c)) was present "
                         "but DORMANT — not yet in force"),
            },
            {
                "start": date(2025, 8, 1),
                "end": None,  # open — current
                "version": "2025-08-01",
                "note": ("the dormant 24-hour rule (31G.3A(c)) was ACTIVATED (24/7 Metering Support "
                         "decision, effective 1 August 2025): suppliers must now keep an enquiry "
                         "service open 24 hours a day for domestic customers off-supply due to a "
                         "faulty meter"),
            },
        ],
    },
    "4A": {
        "title": "Operational capability",
        # INTRODUCED 22 Jan 2021 (Supplier Licensing Review — the same date as 5A/5B/19D;
        # Scott-verified, Ofgem). Absent v2019, present v2022 — before 22 Jan 2021 it did NOT exist
        # (existence boundary). Then a SINGLE text change effective 21 Oct 2022: paragraph 4A.2
        # ("Sufficient Control over the Material Economic and Operational Assets") added. The change
        # is BRACKETED — v2022 (14 Apr 2022) holds the pre-4A.2 introduced text, v2024-07 (1 Jul 2024)
        # the post-4A.2 text (stable through v2025) — so gap-free.
        "introduced": date(2021, 1, 22),   # existence boundary: before this it did NOT exist
        "earliest": date(2021, 1, 22),
        "segments": [
            {
                "start": date(2021, 1, 22),
                "end": date(2022, 10, 21),
                "version": "2022-04-14",
                "note": ("the operational-capability principle as introduced — before paragraph 4A.2 "
                         "(Sufficient Control over the Material Economic and Operational Assets needed "
                         "to run the supply business) was added"),
            },
            {
                "start": date(2022, 10, 21),
                "end": None,  # open — current (text stable v2024-07 through v2025)
                "version": "2025-08-01",
                "note": ("paragraph 4A.2 added (effective 21 October 2022): the licensee must have "
                         "Sufficient Control over the Material Economic and Operational Assets used "
                         "or needed to run its supply business"),
            },
        ],
    },
    "8": {
        "title": "Obligations under Last Resort Supply Direction",
        # Condition 8 predates our corpus (introduced 6 Apr 2007), so `earliest` = 3 Aug 2019
        # knowledge boundary. TWO Scott-verified changes, each bracketed (one per held-version window):
        #  - 22 Jan 2021 (SUBSTANTIVE): added the duty to take all reasonable steps to honour any
        #    commitment made to the Authority before a Last Resort Supply Direction was given (with
        #    consequential paragraph renumbering). v2019 (pre) -> v2022 (post).
        #  - 1 Oct 2022 (COSMETIC): a single cross-reference renumber (6(a) -> 7(a)), no substantive
        #    change. v2022 (pre) -> v2024-07 (post). Mapped as its own segment for per-date TEXT
        #    fidelity (the correctness rule serves the exact text in force on date X), though the
        #    obligations are unchanged across it.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2021, 1, 22),
                "version": "2019-08-03",
                "note": ("before the 22 January 2021 amendment: without the express duty to honour, "
                         "in complying with a Last Resort Supply Direction, any commitment made to "
                         "the Authority before that direction was given"),
            },
            {
                "start": date(2021, 1, 22),
                "end": date(2022, 10, 1),
                "version": "2022-04-14",
                "note": ("as amended 22 January 2021: the licensee must take all reasonable steps to "
                         "honour any commitment made to the Authority before a Last Resort Supply "
                         "Direction was given"),
            },
            {
                "start": date(2022, 10, 1),
                "end": None,  # open — current
                "version": "2025-08-01",
                "note": ("as amended 1 October 2022: a minor cross-reference renumber only (6(a) -> "
                         "7(a)); the substantive obligations are unchanged from the 22 January 2021 text"),
            },
        ],
    },
    "9": {
        "title": "Claims for Last Resort Supply Payment",
        # Condition 9 predates our corpus (Last Resort Supply framework), so `earliest` = 3 Aug 2019
        # knowledge boundary — it is NOT an introduced condition. ONE Scott-verified change effective
        # 6 May 2022: paragraph (ba) added so a Last Resort Supply Payment claim may include finance
        # costs, paragraph 9.7A added governing the transfer/assignment of a claim, and a definition of
        # "Valid Claim" introduced. $0 corpus diff confirms gap-free: v2019 == v2022 (identical pre-
        # change text, both before 6 May 2022) and v2024-07 == v2025 (stable post-change text). The
        # lone v2024-10 blip is proven PDF-extraction noise (scattered single-token OCR errors, e.g.
        # "relatio n" -> "relation"), NOT a second change — v2024-07 and v2025 are byte-identical. So
        # v2022 brackets the change on the pre side and v2024-07 on the post side.
        "earliest": date(2019, 8, 3),
        "segments": [
            {
                "start": date(2019, 8, 3),
                "end": date(2022, 5, 6),
                "version": "2022-04-14",
                "note": ("before the 6 May 2022 amendment: a Last Resort Supply Payment claim did not "
                         "yet expressly provide for finance costs, there was no paragraph 9.7A on "
                         "transferring or assigning a claim, and 'Valid Claim' was not yet defined"),
            },
            {
                "start": date(2022, 5, 6),
                "end": None,  # open — current (text stable v2024-07 through v2025)
                "version": "2025-08-01",
                "note": ("as amended 6 May 2022: paragraph (ba) added so a claim may include the "
                         "finance costs the supplier incurred, paragraph 9.7A added governing the "
                         "transfer or assignment of a claim, and a definition of 'Valid Claim' introduced"),
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
        # For an INTRODUCED condition, "before earliest" means it did NOT exist yet — behave like a
        # pure existence-boundary condition (25E/4D): serve the CURRENT text so the model can state
        # non-existence and describe what the condition now requires, framed by the "did not exist,
        # introduced [date]" temporal note. For a NON-introduced condition, before our earliest held
        # text is genuinely unknown territory → None (caller caveats; asserts no content).
        tc = TEXT_CHANGES.get(condition)
        if tc and tc.get("introduced"):
            return versions.CURRENT_LABEL
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


def citation_note(condition: str, as_of: date) -> str:
    """Short, deterministic version/effective-date note for a citation line, or '' when the
    condition is not version-mapped (its current text simply applies). The app appends this to the
    'Source: Condition X' line so version-awareness is surfaced without relying on the model to echo
    a date. Every date here comes from the verified temporal map, so it is grounded by construction.
    """
    tc = TEXT_CHANGES.get(condition)
    if tc is not None:
        seg = _segment(condition, as_of)
        if seg == "TOO_EARLY":
            # Before our earliest held text. For an introduced condition that means it did not exist.
            if tc.get("introduced"):
                return f"introduced {fmt(tc['introduced'])}; did not exist as of {fmt(as_of)}"
            return ""
        if not seg:
            return ""
        v = versions.BY_LABEL[seg["version"]]
        note = f"consolidated to {fmt(v['date'])}"
        # A segment's start is a REAL effective date only for an introduced condition (first segment
        # = its introduction) or for any LATER segment (a genuine change date). The first segment of a
        # non-introduced condition merely starts at our earliest held consolidation, which is not an
        # effective date — so don't present it as one.
        idx = tc["segments"].index(seg)
        if tc.get("introduced") or idx > 0:
            note += f"; this wording effective from {fmt(seg['start'])}"
        return note
    m = MAPPED.get(condition)
    if m is not None:
        if as_of >= m["introduced"]:
            return f"introduced {fmt(m['introduced'])}"
        return f"introduced {fmt(m['introduced'])}; did not exist as of {fmt(as_of)}"
    return ""


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
            if tc.get("introduced"):
                # Introduced condition: before its introduction it genuinely DID NOT EXIST — assert
                # that (existence boundary), NOT the weaker "text not held" caveat used when a
                # condition existed earlier but we simply don't hold its historic consolidation.
                notes.append(
                    f"Condition {c} ({tc['title']}) was introduced into the licence on "
                    f"{fmt(tc['introduced'])}. As of {fmt(as_of)} it did NOT yet exist — do not "
                    f"present any obligation under it as applying on that date."
                )
            else:
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
