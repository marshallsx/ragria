"""
Phase 6 — Held-version registry (multi-version corpus).

Single source of truth for the consolidated licence versions we have INGESTED.
"Current" is derived here as the latest held version — a role, not a fixed date —
so ingesting a newer consolidation later is a one-line change (add an entry) and
everything downstream (temporal facts, retrieval filter, UI caption) follows.

Each version is a dated Ofgem consolidation. We hold two that bracket the
Condition 28 (Prepayment Meters) text change of 8 November 2023:
  - v2022 (14 Apr 2022) — the pre-reform text
  - v2025 (1 Aug 2025)  — the current, post-reform text
v2019 (3 Aug 2019) is on disk but not yet ingested (Condition 28 was unchanged
2019→2022, so v2022 already covers the whole pre-change period).
"""
from __future__ import annotations

from datetime import date

VERSIONS: list[dict] = [
    {
        "label": "2022-04-14",
        "date": date(2022, 4, 14),
        "pdf": "electricity-supply-slc-consolidated-2022-04-14.pdf",
        "cache": "slc_pages_2022-04-14.jsonl",
        "doc_title": "Electricity Supply Standard Licence Conditions (consolidated to 14 April 2022)",
        "authority": "consolidated",  # reference, not the definitive EPR register
        "url": "https://www.ofgem.gov.uk/sites/default/files/2022-05/Electricity%20Supply%20Standard%20Consolidated%20Licence%20Conditions.pdf",
        "body_start": 7,  # cover=1, ToC=2..6 (same front-matter structure as v2025)
    },
    {
        "label": "2025-08-01",
        "date": date(2025, 8, 1),
        "pdf": "electricity-supply-slc-consolidated-2025-08.pdf",
        "cache": "slc_pages_2025-08-01.jsonl",
        "doc_title": "Electricity Supply Standard Licence Conditions (consolidated to 1 August 2025)",
        "authority": "consolidated",
        "url": "https://www.ofgem.gov.uk/sites/default/files/2025-08/Electricity-Supply-Standard-Consolidated-Licence-Conditions.pdf",
        "body_start": 7,  # cover=1, ToC=2..6
    },
]

BY_LABEL: dict[str, dict] = {v["label"]: v for v in VERSIONS}

# "Current" = the latest held version. Never hardcode a specific date elsewhere.
CURRENT: dict = max(VERSIONS, key=lambda v: v["date"])
CURRENT_LABEL: str = CURRENT["label"]
CURRENT_DATE: date = CURRENT["date"]
