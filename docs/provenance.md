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
- Verified: Condition 28's text is unchanged 3 Aug 2019 → 14 Apr 2022, so this snapshot
  correctly represents the pre-reform text for the whole period up to 8 Nov 2023.

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
