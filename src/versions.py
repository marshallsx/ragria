"""
Phase 6 — Held-version registry (multi-version corpus).

Single source of truth for the consolidated licence versions we have INGESTED.
"Current" is derived here as the latest held version — a role, not a fixed date —
so ingesting a newer consolidation later is a one-line change (add an entry) and
everything downstream (temporal facts, retrieval filter, UI caption) follows.

Each version is a dated Ofgem consolidation. We hold five:
  - v2019 (3 Aug 2019)  — earliest; opens up pre-2022 (2019→2022) text-change conditions
  - v2022 (14 Apr 2022) — pre-reform side of the Condition 28 / 0A changes
  - v2024-07 (1 Jul 2024) — archived; splits the old 2022→2025 blind spot
  - v2024-10 (1 Oct 2024) — archived; brackets late-2024 changes (e.g. Cond 60 intro)
  - v2025 (1 Aug 2025)  — the current text (derived as CURRENT)

The two 2024 consolidations were recovered from the Wayback Machine (Ofgem overwrites its
"Current" URL in place); they are held for FUTURE mappings and are inert in retrieval until a
condition's timeline points at them — default/undated answers are unaffected (retrieval is
scoped to CURRENT, still 2025-08-01). See docs/provenance.md for the archive provenance.
"""
from __future__ import annotations

from datetime import date

VERSIONS: list[dict] = [
    {
        "label": "2019-08-03",
        "date": date(2019, 8, 3),
        "pdf": "electricity-supply-slc-consolidated-2019-08-03.pdf",
        "cache": "slc_pages_2019-08-03.jsonl",
        "doc_title": "Electricity Supply Standard Licence Conditions (consolidated to 3 August 2019)",
        "authority": "consolidated",
        "url": "https://www.ofgem.gov.uk/sites/default/files/docs/2020/07/electricity_supply_standard_license_conditions.pdf",
        "body_start": 7,  # cover=1, ToC=2..6 (same front-matter structure as v2022/v2025)
    },
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
        # Recovered from the Wayback Machine's capture of Ofgem's overwritten
        # ".../2023-03/…- Current.pdf" (that URL is updated in place; the archive holds the
        # texts it used to serve). Self-identifies in its header as "Consolidated to 1 July 2024".
        # Provenance is one notch below the direct-download consolidations — see docs/provenance.md.
        "label": "2024-07-01",
        "date": date(2024, 7, 1),
        "pdf": "electricity-supply-slc-consolidated-2024-07-01.pdf",
        "cache": "slc_pages_2024-07-01.jsonl",
        "doc_title": "Electricity Supply Standard Licence Conditions (consolidated to 1 July 2024)",
        "authority": "consolidated-archived",  # Wayback capture of an overwritten Ofgem URL
        "url": "https://web.archive.org/web/20240823130511id_/https://www.ofgem.gov.uk/sites/default/files/2023-03/Electricity%20Supply%20Standard%20Consolidated%20Licence%20Conditions%20-%20Current.pdf",
        "body_start": 7,  # cover=1, ToC=2..6 (same front-matter structure as the others)
    },
    {
        # Wayback capture as above; self-identifies as "Consolidated to 01 October 2024".
        "label": "2024-10-01",
        "date": date(2024, 10, 1),
        "pdf": "electricity-supply-slc-consolidated-2024-10-01.pdf",
        "cache": "slc_pages_2024-10-01.jsonl",
        "doc_title": "Electricity Supply Standard Licence Conditions (consolidated to 1 October 2024)",
        "authority": "consolidated-archived",
        "url": "https://web.archive.org/web/20250211205540id_/https://www.ofgem.gov.uk/sites/default/files/2023-03/Electricity%20Supply%20Standard%20Consolidated%20Licence%20Conditions%20-%20Current.pdf",
        "body_start": 7,
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
