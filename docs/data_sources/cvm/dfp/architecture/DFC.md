<- Back to [DFP Architecture](../ARCHITECTURE.md)

# 💧 DFC — Demonstração do Fluxo de Caixa (Cash Flow Statement)

The DFC is the Brazilian cash flow statement. CVM assigns codes in the
`6.xx` range. The standalone `dfc` mode (v1.11) surfaces 6 codes verified
against real DFP data (rows range from 6021 to 6628).

## 📊 DFC methods: DFC_MI vs DFC_MD

CVM DFP allows filers to use one of two cash-flow methods:

| Method | grupo substring | Rows in real DFP | % of filers | Who uses it |
|--------|-----------------|------------------|-------------|-------------|
| **DFC_MI** (Método Indireto) | `DF Consolidado - Fluxo de Caixa - Método Indireto` | 318873 | **98.6%** | Almost all non-financial filers |
| **DFC_MD** (Método Direto) | `DF Consolidado - Fluxo de Caixa - Método Direto` | 4433 | **1.4%** | Banks + insurers |

The `grupo LIKE '%Fluxo de Caixa%'` filter matches BOTH methods — so the
standalone `dfc` mode and the DFC engines (`operating_cf`, `investing_cf`,
`financing_cf`, `da`) surface rows from both groups in a single query.

## ⚠️ D&A code issues (CRITICAL)

Depreciação e Amortização (D&A) is a non-cash expense added back to net
income under the indirect method. It is reported under DFC code `6.01.01.02`
for ~98.6% of filers (DFC_MI). The v1.2 codebase added two fallback codes
for the rare DFC_MD filers; v1.11 re-audited them against real DFP data:

| Code | v1.2 label | Real DFP `descricao` | Real rows | v1.11 status |
|------|------------|----------------------|-----------|--------------|
| `6.01.01.02` | "Depreciação e Amortização (Método Indireto)" | "Depreciação e Amortização" | **6021** | ✅ Primary — kept |
| `6.02.01.02` | "Depreciação e Amortização (Método Direto)" | (none — code never used) | **0** | ⚠️ Dead fallback — kept for completeness (no-op, returns None) |
| `6.01.04` | "Depreciação e Amortização (DFC_MD alt)" | "Pagamentos à Fornecedores" | **11** | ❌ **MISLABEL — removed in v1.11** |

### Why `6.01.04` was removed

v1.2 added `6.01.04` as a "DFC_MD alt" fallback in `_extract_metrics`,
assuming it was an alternative D&A sub-account for direct-method filers.
Real DFP data reveals it is actually "Pagamentos à Fornecedores" (supplier
payments — an operating outflow, NOT a non-cash adjustment). For any filer
that populated `6.01.04`, the v1.2 fallback would silently have returned
**supplier payments as D&A** — corrupting EBITDA = EBIT + D&A.

v1.11 actions:
1. Removed `6.01.04` from `SUMMARY_CODES` (`metrics.py`).
2. Removed `6.01.04` from the `_extract_metrics` D&A fallback chain
   (`fetchers.py`). Chain is now `6.01.01.02 → 6.02.01.02 → None`.
3. Updated the `test_metrics.py` + `test_financials.py` regression tests:
   `TestDFCMDFallback.test_da_direct_method_alt_fallback` now asserts
   `da is None` when only `6.01.04` is provided (was `da == 2000.0`).
4. Added an audit note to `skills/cvm/calculations/engines/dfc/da.py` clarifying
   that the `da_at` engine itself never used `6.01.04` — it relies on
   `descricao LIKE '%deprec%' OR '%amort%'` search, scoped to
   `codigo LIKE '6.01.%'` (operating section).

### Why `6.02.01.02` was kept despite 0 rows

It is a *dead* code path (returns `None` silently) but not a *wrong* one.
No filer populates it, so the fallback is harmless. Kept for completeness
in case CVM adds data under that code in future filings.

## Chart of accounts (6 codes, v1.11+)

| Code | Canonical label | Section | Notes |
|------|-----------------|---------|-------|
| `6.01`       | Caixa Líquido Atividades Operacionais (FCO) | operating | 6628 rows. Net cash from operating activities. Used by `operating_cf_at` engine + `_extract_metrics` (`fco`). |
| `6.01.01.02` | Depreciação e Amortização | da | 6021 rows. Primary D&A code (indirect method). Used by `da_at` engine + `_extract_metrics` (`da`). ⚠️ See D&A code issues above. |
| `6.02`       | Caixa Líquido Atividades de Investimento (FCI) | investing | 6627 rows. Used by `investing_cf_at` engine + `_extract_metrics` (`fci`). |
| `6.03`       | Caixa Líquido Atividades de Financiamento (FCF) | financing | 6628 rows. Used by `financing_cf_at` engine + `_extract_metrics` (`fcf`). |
| `6.04`       | Variação Cambial s/ Caixa e Equivalentes | fx_change | [v1.11] NEW. FX variation on cash + equivalents. Typically 0 for non-USD filers; can be significant for exporters (PETR4/VALE3). Added to SUMMARY_CODES + `_extract_metrics` (`variacao_cambial`) + `KEY_CODES_BY_GRUPO["DFC_MI"]` + standalone `dfc` mode in v1.11. |
| `6.05`       | Aumento (Redução) de Caixa e Equivalentes | net_change | [v1.11] NEW. Net cash + equivalents change (= FCO + FCI + FCF + 6.04). Useful as a sanity check that DFC flows reconcile to the balance-sheet change in `1.01.01` (Caixa e Equivalentes). Added to SUMMARY_CODES + `_extract_metrics` (`variacao_caixa`) + `KEY_CODES_BY_GRUPO["DFC_MI"]` + standalone `dfc` mode in v1.11. |

## grupo filter (DFC vs other statements)

DFP stores the DFC `grupo` value as:

| grupo | Statement | Method |
|-------|-----------|--------|
| `DF Consolidado - Fluxo de Caixa - Método Indireto` | **DFC_MI** (this mode) | Indirect (98.6% of filers) |
| `DF Consolidado - Fluxo de Caixa - Método Direto` | **DFC_MD** (this mode) | Direct (1.4% — banks + insurers) |
| `DF Individual - Fluxo de Caixa - Método Indireto` | **DFC_MI** (individual) | Indirect |
| `DF Individual - Fluxo de Caixa - Método Direto` | **DFC_MD** (individual) | Direct |

The standalone DFC mode filters by `grupo LIKE '%Fluxo de Caixa%'` — this
matches BOTH methods (DFC_MI + DFC_MD) and BOTH consolidation levels
(consolidated + individual). Since codes `6.xx` are unique to the DFC
statement (BPA uses `1.xx`, BPP uses `2.xx`, DRE uses `3.xx`, DVA uses
`7.xx`), the code-list filter (`codigo IN (...)`) is sufficient on its
own — but the grupo filter is included as a safety net for future CVM
schema changes.

## How the financials skill uses these codes

### `mode="dfc"` (v1.11, standalone)

Surfaces ALL 6 codes above, with `label` + `section` + `valor_brl` per
period. Filters `grupo LIKE '%Fluxo de Caixa%'`. Supports both annual
(DFP, `meses=12`) and quarterly (ITR `meses=3/6/9` + DFP `meses=12`).

### `SUMMARY_CODES` (annual / quarterly / summary / dashboard)

The summary modes use a curated subset of DFC codes for ratio
computation. After v1.11 the SUMMARY_CODES for DFC are:

| Code | Metric key in `_extract_metrics` |
|------|----------------------------------|
| `6.01` | `fco` (FCO — operating cash flow) |
| `6.01.01.02` | `da` (D&A for EBITDA — with `6.02.01.02` fallback; `6.01.04` removed in v1.11) |
| `6.02` | `fci` (FCI — investing cash flow) |
| `6.03` | `fcf` (FCF — financing cash flow) |
| `6.04` | `variacao_cambial` (NEW v1.11 — FX variation on cash) |
| `6.05` | `variacao_caixa` (NEW v1.11 — net cash change) |
| `6.02.01.02` | (kept as D&A fallback — 0 rows in real DFP, dead code path) |

### `complete` mode

`KEY_CODES_BY_GRUPO["DFC_MI"]` (after v1.11): the full 6-code list above.
Codes 6.xx are unique to DFC so no overlap with BPA/BPP/DRE/DVA.

## Impact on existing engines

### `da_at` engine (uses `descricao LIKE '%deprec%' OR '%amort%'`)

The `da_at` engine in `skills/cvm/calculations/engines/dfc/da.py` does NOT
use code-level fallbacks — it searches by `descricao` (with section
scoping `codigo LIKE '6.01.%'` and accent-normalized exclusion of
financing lines like "Amortização de Empréstimos"). v1.11 audit confirms
it never depended on `6.01.04`; the removal in `_extract_metrics` does
not affect this engine.

### `operating_cf_at` / `investing_cf_at` / `financing_cf_at` engines

These engines query `6.01` / `6.02` / `6.03` directly. v1.11 changes do
not affect them.

### `_extract_metrics` (in `fetchers.py`)

D&A fallback chain after v1.11: `6.01.01.02 → 6.02.01.02 → None`.
Previously: `6.01.01.02 → 6.02.01.02 → 6.01.04 → None`.

## Common pitfalls

1. **`6.01.04` is NOT D&A.** It is "Pagamentos à Fornecedores" (supplier
   payments — an operating outflow). v1.2 mistakenly added it as a D&A
   fallback in `_extract_metrics`; v1.11 removed it. If you see D&A
   values that look like supplier-payment magnitudes for a DFC_MD filer,
   suspect the old (v1.2-v1.10) code path.

2. **`6.02.01.02` has 0 rows in real DFP.** It is a dead fallback code
   path. Kept for completeness (returns None silently, no harm). If CVM
   ever populates it, the fallback will activate automatically.

3. **DFC_MD filers (1.4% — banks, insurers) often have no D&A in
   standardized codes.** For these filers, D&A is only recoverable via
   the description search in `da_at` (and indirectly in
   `compute_ebitda_from_engines`). The `_extract_metrics` chain returns
   None for them, causing `compute_ebitda` to fall back to
   `"ebit_only"` (EBITDA = EBIT).

4. **DFC is available in BOTH DFP and ITR.** Annual DFC comes from DFP
   (`meses=12`). Quarterly cumulative DFC comes from ITR (`meses=3/6/9`).
   The `dfc` mode with `quarterly=1` queries both. DFC is a FLOW statement
   (cumulative within the year), so standalone quarter derivation requires
   subtraction: Q2 = cum6 − cum3, Q4 = DFP annual − cum9.

5. **`6.04` and `6.05` are flow items, not snapshots.** They are
   cumulative within the year, same as `6.01`-`6.03`. The standalone
   `dfc` mode returns the cumulative value; the quarterly summary mode
   (`_extract_metrics` keys `variacao_cambial` + `variacao_caixa`)
   returns the standalone-derived value (Q1 = cum3, Q2 = cum6 − cum3,
   etc.).

6. **DFC is NOT DRE.** DRE (codes 3.xx) is the income statement. DFC
   (codes 6.xx) is the cash flow statement. The two share many concepts
   (operating, investing, financing) but the values differ — DRE uses
   accrual accounting; DFC uses cash accounting. D&A appears in BOTH
   (DRE as a depreciation expense within operating costs; DFC as a
   non-cash adjustment to net income). The EBITDA formula uses DFC's
   D&A (code `6.01.01.02`), NOT DRE's.

7. **DFC is NOT DVA.** DVA (codes 7.xx) is the value-added statement.
   DFC (codes 6.xx) is the cash flow statement. Different concepts —
   DFC tracks cash movements; DVA tracks value created and distributed.

---

*Last updated: 2026-07-30 (v1.11 — created alongside the standalone `dfc` mode + 6.04/6.05 added to SUMMARY_CODES + 6.01.04 mislabel fix).*
