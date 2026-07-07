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
