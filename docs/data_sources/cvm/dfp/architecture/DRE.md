<- Back to [DFP Architecture](../ARCHITECTURE.md)

# 📊 DRE — Demonstração do Resultado do Exercício

The DRE is the Brazilian income statement. CVM assigns codes in the `3.xx`
range. All 10 engine codes verified to exist in real DFP data (6628–6629 rows
each, except `3.11` with 6377 rows).

## Chart of accounts

| Code | Canonical label | Section | Notes |
|------|-----------------|---------|-------|
| `3.01` | Receita Líquida de Vendas e/ou Serviços | revenue | Some filers (banks) use **"Receitas da Intermediação Financeira"** instead. |
| `3.02` | Custo dos Bens e/ou Serviços Vendidos | costs | COGS — negative value (expense). |
| `3.03` | Resultado Bruto | gross_profit | `3.01 − 3.02`. Banks use **"Resultado Bruto Intermediação Financeira"**. |
| `3.04` | Despesas Administrativas, Gerais e Comerciais | operating_expenses | Parent code for operating expenses. |
| `3.05` | Resultado Antes do Resultado Financeiro e dos Tributos | ebit | Also labeled **"Resultado Antes dos Tributos sobre o Lucro"**. EBIT in the EBITDA formula. |
| `3.06` | Resultado Financeiro | financial_result | ⚠️ **ALSO labeled "Imposto de Renda"** by some filers (CVM chart changed over years). |
| `3.07` | Resultado Líquido das Operações Continuadas | net_continuing | ⚠️ **Was missing from `SUMMARY_CODES` prior to v1.8** — added in this version. |
| `3.08` | Imposto de Renda e Contribuição Social sobre o Lucro | tax | ⚠️ **ALSO labeled "Operações Descontinuadas"** by some filers. |
| `3.09` | Lucro/Prejuízo Consolidado do Período | net_income | Some filers use this as the final net income. |
| `3.11` | Lucro/Prejuízo Consolidado do Período (alt) | net_income_alt | Some filers use this instead of `3.09` (6377 rows vs 6629). Some use `3.13`. |

## grupo filter (DRE vs DRA distinction)

DFP stores FOUR `grupo` values that match the substring "Resultado":

| grupo | Statement |
|-------|-----------|
| `DF Consolidado - Demonstração do Resultado` | **DRE** (this mode) |
| `DF Consolidado - Demonstração de Resultado Abrangente` | **DRA** — comprehensive income; DIFFERENT statement |
| `DF Individual - Demonstração do Resultado` | **DRE** (individual) |
| `DF Individual - Demonstração de Resultado Abrangente` | **DRA** (individual) |

The DRE standalone mode filters by `grupo LIKE '%Demonstração do Resultado%'`.
This matches BOTH DRE and DRA — but since DRE codes (`3.xx`) are NOT used in
DRA, the code-list filter (`codigo IN (...)`) excludes DRA rows in practice.

> **Historical note:** in CVM's older chart (pre-2010s reform), some filers
> filed a unified "Demonstração de Resultado Abrangente" that combined DRE +
> DRA. The `3.xx` codes are still attached to the DRE rows in those filings.

## How the financials skill uses these codes

### `mode="dre"` (v1.8, standalone)

Surfaces ALL 10 codes above, with `label` + `section` + `valor_brl` per
period. Filters `grupo LIKE '%Demonstração do Resultado%'`. Supports both
annual (DFP, `meses=12`) and quarterly (ITR `meses=3/6/9` + DFP `meses=12`).

### `SUMMARY_CODES` (annual / quarterly / summary / dashboard)

The summary modes use a curated subset of the DRE codes for ratio
computation. After v1.8 the SUMMARY_CODES for DRE are:

| Code | Metric key in `_extract_metrics` |
|------|----------------------------------|
| `3.01` | `receita_liquida` |
| `3.03` | `lucro_bruto` |
| `3.05` | `ebit` (used by `compute_ebitda`) |
| `3.06` | `resultado_financeiro` |
| `3.07` | `resultado_liquido_continuadas` (NEW v1.8) |
| `3.09` | (in SUMMARY_CODES but not extracted — historical) |
| `3.11` | `lucro_liquido` |

### `complete` mode

`KEY_CODES_BY_GRUPO["DRE"]` (after v1.8):
`["3.01", "3.02", "3.03", "3.04", "3.04.02", "3.05", "3.06", "3.07", "3.09", "3.11"]`

## Common pitfalls

1. **Code 3.06 sometimes means tax, not financial result.** The CVM chart of
   accounts changed between filing years. When the description in the row is
   "Imposto de Renda", the value is a tax, not a financial result. The
   standalone DRE mode surfaces the raw value with the canonical label;
   callers needing precise semantics should filter by `descricao` as well.

2. **Code 3.11 has 252 fewer rows than 3.09.** Some filers (mostly smaller
   companies and a few sectors) end their DRE at `3.09` instead of `3.11`.
   The `dva` mode's net-income extraction prefers `3.11` but the
   calculations engine `ttm_earnings_at` falls back to `3.09` via
   description-search when `3.11` is missing.

3. **3.07 was missing from SUMMARY_CODES prior to v1.8.** Real DFP data has
   6629 rows for 3.07 — it's a real code that sits between 3.06 (Resultado
   Financeiro) and 3.08 (Imposto de Renda). v1.8 added it.

4. **DRA is NOT DRE.** `grupo LIKE '%Resultado Abrangente%'` returns the
   comprehensive income statement (DRA), which is a separate statement.
   Don't confuse the two filters — DRE mode uses `'%Demonstração do
   Resultado%'`.

---

*Last updated: 2026-07-30 (v1.8 — created alongside the standalone `dre` mode).*
