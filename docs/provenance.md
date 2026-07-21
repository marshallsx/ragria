# Corpus Provenance

Record of all source documents ingested by RAGRIA. **Public Ofgem data only** — no
Centrica / British Gas internal, confidential, or proprietary material.

> `data/` is gitignored, so the source files themselves are not on GitHub. This file
> is the tracked record of where each one came from and when it was retrieved.

---

## 1. Electricity Supply — Standard Licence Conditions (consolidated)

| Field | Value |
|---|---|
| **Local file** | `data/raw/electricity-supply-slc-consolidated-2025-08.pdf` |
| **Document** | Standard conditions of the electricity supply licence (consolidated) |
| **Issuer** | Ofgem / Gas and Electricity Markets Authority (Electricity Act 1989) |
| **Consolidated to** | 1 August 2025 |
| **Source URL** | https://www.ofgem.gov.uk/sites/default/files/2025-08/Electricity-Supply-Standard-Consolidated-Licence-Conditions.pdf |
| **Retrieved** | 2026-07-07 |
| **Server last-modified** | 2025-08-20 |
| **Size / pages** | 3.7 MB · 611 pages |
| **Format** | PDF 1.7, extractable text (verified via pdfplumber) |
| **Licence / access** | Publicly available on Ofgem's website |

**Notes:**
- Ofgem flags that *consolidated* conditions are "not formal Public Register documents
  and should not be relied on." The authoritative live version is the **Current Version**
  on the Electronic Public Register:
  https://epr.ofgem.gov.uk/Content/Documents/Electricity%20Supply%20Standard%20Licence%20Conditions%20Consolidated%20-%20Current%20Version.pdf
  For a learning PoC we use the dated, stable consolidated PDF for reproducibility.
- Every page repeats a header note + running title; strip these during chunking (Phase 2)
  so they don't pollute retrieval.
- Scope for v0: **electricity only** (gas noted for later).

---

## 2. Electricity Supply — SLCs, consolidated to 14 April 2022 (historic version)

Ingested in Phase 6 (temporal / version awareness) as the **pre-reform** side of the
Condition 28 (Prepayment Meters) text change of 8 November 2023.

| Field | Value |
|---|---|
| **Local file** | `data/raw/electricity-supply-slc-consolidated-2022-04-14.pdf` |
| **Document** | Standard conditions of the electricity supply licence (consolidated) |
| **Issuer** | Ofgem / Gas and Electricity Markets Authority (Electricity Act 1989) |
| **Consolidated to** | 14 April 2022 |
| **Source URL** | https://www.ofgem.gov.uk/sites/default/files/2022-05/Electricity%20Supply%20Standard%20Consolidated%20Licence%20Conditions.pdf |
| **Retrieved** | 2026-07-08 |
| **Size / pages** | 3.2 MB · 550 pages |
| **Format** | PDF, extractable text (verified via pypdf) |
| **Licence / access** | Publicly available on Ofgem's website |

**Notes:**
- Same "not formal Public Register documents / should not be relied on" caveat as the
  current version; used here for reproducibility of the historic text.
- ~~Verified: Condition 28's text is unchanged 3 Aug 2019 → 14 Apr 2022, so this snapshot
  correctly represents the pre-reform text for the whole period up to 8 Nov 2023.~~
  **WRONG — corrected.** Condition 28 *did* change in that interval: paragraph (bb)
  (Emergency Credit, Friendly-hours Credit, Additional Support Credit, "as defined in
  SLC 27A") was inserted effective **15 Dec 2020**, by the same s.11A modification that
  introduced SLC 27A and amended SLC 27. The v2022 snapshot is therefore the correct text
  only from 15 Dec 2020; **v2019 carries the text for 3 Aug 2019 → 15 Dec 2020**, and
  `temporal.py` now splits the segment accordingly.
  The original claim came from a change detector using a 0.97 similarity threshold, which
  scored this insertion 0.973 and reported "unchanged". Detection is now exact (c55ea2d).

## 3. Electricity Supply — SLCs, consolidated to 3 August 2019 (historic version)

Ingested to open up **pre-2022** text-change conditions (those that changed between the
3 Aug 2019 and 14 Apr 2022 consolidations).

| Field | Value |
|---|---|
| **Local file** | `data/raw/electricity-supply-slc-consolidated-2019-08-03.pdf` |
| **Document** | Standard conditions of the electricity supply licence (consolidated) |
| **Issuer** | Ofgem / Gas and Electricity Markets Authority (Electricity Act 1989) |
| **Consolidated to** | 3 August 2019 |
| **Source URL** | https://www.ofgem.gov.uk/sites/default/files/docs/2020/07/electricity_supply_standard_license_conditions.pdf |
| **Retrieved** | 2026-07-08 |
| **Size / pages** | 4.2 MB · 484 pages |
| **Format** | PDF, extractable text (verified via pypdf) |
| **Licence / access** | Publicly available on Ofgem's website |

**Notes:**
- Same "not formal Public Register documents / should not be relied on" caveat as the
  other consolidations; used for reproducibility of the historic text.
- Ingested as version-tagged chunks alongside v2022 and v2025 (89 conditions → 918 chunks).

## 4 & 5. Electricity Supply — SLCs, consolidated to 1 July 2024 and 1 October 2024 (archived)

Two intermediate consolidations recovered to split the old 14 Apr 2022 → 1 Aug 2025 blind
spot (3 years 4 months) into three windows. Held for FUTURE temporal mappings (e.g. Cond 31G,
whose Dec 2023 and 1 Aug 2025 changes these two snapshots bracket; the Cond 60 introduction
between Jul and Oct 2024). **Inert in retrieval** until a condition's timeline points at them —
default/undated answers are unaffected (retrieval is scoped to the current version).

| Field | 1 July 2024 | 1 October 2024 |
|---|---|---|
| **Local file** | `data/raw/electricity-supply-slc-consolidated-2024-07-01.pdf` | `…-2024-10-01.pdf` |
| **Consolidated to** | 1 July 2024 (self-identified in header) | 01 October 2024 (self-identified) |
| **Pages / conditions** | 607 pp · 110 conditions · 1126 chunks | 608 pp · 111 conditions · 1129 chunks |
| **Original last-modified** | 29 Jul 2024 (from archive headers) | 1 Oct 2024 |
| **Retrieved** | 2026-07-21 | 2026-07-21 |
| **Format** | PDF 1.7, extractable text (verified via pypdf) | same |

**Provenance — read this honestly:**
- ⚠️ **These are NOT direct downloads from Ofgem's live site.** They were recovered from the
  **Wayback Machine**, which had captured Ofgem's `.../2023-03/…- Current.pdf` URL at earlier
  dates. Ofgem **overwrites that "Current" URL in place** (it now serves the 1 Aug 2025 text),
  so the only way to obtain the intermediate consolidations it used to serve is via the archive.
- **Archive capture URLs (the actual source):**
  - v2024-07: `https://web.archive.org/web/20240823130511id_/https://www.ofgem.gov.uk/sites/default/files/2023-03/Electricity%20Supply%20Standard%20Consolidated%20Licence%20Conditions%20-%20Current.pdf`
  - v2024-10: `https://web.archive.org/web/20250211205540id_/…same path…`
- **Still public Ofgem material** — these are Ofgem's own published consolidations, captured by a
  third-party public archive; no non-public data. The project's "public Ofgem data only" rule holds.
- **Authenticity evidence:** each self-identifies in its header ("Consolidated to 1 July 2024" /
  "01 October 2024"), parses with the production chunker into the expected condition progression
  (89 → 105 → **110 → 111** → 111), and the archive records original `last-modified` dates matching
  the consolidation dates. `authority` is tagged `consolidated-archived` in `src/versions.py` — one
  notch below the three direct-download consolidations, upgradable if ever re-downloaded from Ofgem.
- Ingested 2026-07-21; store rebuilt to 5306 chunks. Gate `results_ingest_2024.json` confirmed
  undated/temporal behaviour unchanged (41/41 decisions, faithfulness 37/37, 0 false refusals).
