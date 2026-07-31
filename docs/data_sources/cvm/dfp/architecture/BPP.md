<- Back to [DFP Architecture](../ARCHITECTURE.md)

# 📊 BPP — Balanço Patrimonial Passivo (Balance Sheet — Liabilities + Equity)

The BPP is the Brazilian balance sheet's liabilities + equity side. CVM
assigns codes in the `2.xx` range. All 17 engine codes verified to exist in
real DFP data (rows range from 6355 to 6681).

## ⚠️ The 2.03 meaning trap (OLD vs NEW chart)

The CVM BPP chart of accounts has **CHANGED over the years**. Code `2.03`
exists in BOTH the old chart and the new chart but **has DIFFERENT meanings**
in each — and the new meaning is dangerous (debt masquerading as equity).

| Code | OLD chart label (pre-reform filers) | NEW chart label (post-reform filers) |
|------|-------------------------------------|--------------------------------------|
| `2.01` | Passivo Circulante | Passivos Financeiros para Negociação |
| `2.02` | Passivo Não Circulante | Outros Passivos Financeiros |
| `2.03` | **Patrimônio Líquido** (equity!) | **Passivos Financeiros ao Custo Amortizado** (DEBT!) |
| `2.04` | (not used in OLD chart) | Provisões |
| `2.05` | (not used in OLD chart) | Passivos Fiscais |
| `2.06` | (not used in OLD chart) | Outros Passivos |
| `2.07` | (not used in OLD chart) | Passivos sobre Ativos Não Correntes |
| `2.08` | (not used in OLD chart) | Patrimônio Líquido Consolidado (PL moves here) |

In the NEW chart, **`2.03` is no longer equity** — it is amortized-cost
financial liabilities (debt). Patrimônio Líquido moves to `2.08`. The
financials skill's `patrimonio_liquido` engine queries `2.03` directly, so:

- **Old-chart filers (95% of rows — 6352/6681)**: `2.03` = PL ✓ correct
- **New-chart filers (5% of rows)**: `2.03` = amortized-cost debt ✗ wrong
  (PL would be at `2.08` instead)

This is a **data correctness issue, not a code bug**. The engine returns
whatever `2.03` happens to be for that filer. Callers needing precise
semantics should filter by `descricao` as well, or check whether `2.08`
exists (only present in the NEW chart) and read PL from `2.08` instead.

The standalone `bpp` mode (v1.10) surfaces the raw value with the canonical
label "Patrimônio Líquido" for code `2.03` (matches the OLD chart, which
95% of filers use) and "Patrimônio Líquido (novo formato)" for code `2.08`
(the NEW chart's PL location). The per-row `descricao` from DFP is preserved
in the underlying row but the mode returns the canonical label.

## ⚠️ Multiple labels per code 2.01.01

Code `2.01.01` (6476 rows) has **MULTIPLE descriptions across filers** —
unlike `1.01` in BPA where the chart drift is between two well-defined
formats, `2.01.01` is a "grab bag" of related payables concepts:

| Description | Approximate rows | Notes |
|-------------|------------------|-------|
| Obrigações Sociais e Trabalhistas | 6317 | Most common — payroll + labor obligations |
| Fornecedores | (subset) | Trade payables (some filers use this) |
| Contas a Pagar | (subset) | Generic "payables" (some filers use this) |
| Depósitos | (subset) | Deposits (some filers use this) |

The financials skill's `fornecedores` engine (added v1.10) queries `2.01.01`
and gets whatever the filer uses — most often "Obrigações Sociais e
Trabalhistas" (labor obligations), NOT trade payables despite the engine's
name. The canonical label in `_BPP_CODES` is "Fornecedores / Obrigações"
to reflect this ambiguity. Callers needing precise semantics should filter
by `descricao` as well.

## Chart of accounts (17 codes, v1.10+)

| Code | Canonical label | Section | Notes |
|------|-----------------|---------|-------|
| `2`       | Passivo Total | total | 6681 rows. Grand total liabilities + equity. |
| `2.01`    | Passivo Circulante | current | 6681 rows. ⚠️ NEW chart = "Passivos Financeiros para Negociação" (chart drift). |
| `2.01.01` | Fornecedores / Obrigações | payables | 6476 rows. ⚠️ MULTIPLE descriptions per filer (most common: "Obrigações Sociais e Trabalhistas" at 6317 rows). [v1.10] Added to SUMMARY_CODES + `_extract_metrics` (`fornecedores`). |
| `2.01.04` | Empréstimos e Financiamentos (Circulante) | debt_short | 6363 rows. Short-term debt. |
| `2.02`    | Passivo Não Circulante | non_current | 6681 rows. ⚠️ NEW chart = "Outros Passivos Financeiros" (chart drift). |
| `2.02.01` | Empréstimos e Financiamentos (Não Circ.) | debt_long | 6507 rows. Long-term debt. |
| `2.03`    | Patrimônio Líquido | equity | 6681 rows. ⚠️ **2.03 meaning trap**: OLD chart = PL (6352 rows, 95%); NEW chart = amortized-cost debt. |
| `2.03.01` | Capital Social | capital | 6579 rows. [v1.10] Added to SUMMARY_CODES + `_extract_metrics` (`capital_social`). |
| `2.03.02` | Reservas de Capital | reserves_capital | 6558 rows. [v1.10] Added to SUMMARY_CODES + `_extract_metrics` (`reservas_capital`). |
| `2.03.04` | Reservas de Lucros | reserves_profit | 6480 rows. [v1.10] Added to SUMMARY_CODES + `_extract_metrics` (`reservas_lucros`). |
| `2.03.05` | Lucros Acumulados | retained_earnings | 6453 rows. [v1.10] Added to SUMMARY_CODES + `_extract_metrics` (`lucros_acumulados`). |
| `2.03.09` | Participação Não Controladores | minority | 6355 rows. Non-controlling interest. [v1.10] Added to SUMMARY_CODES + `_extract_metrics` (`minority_interest`). |
| `2.04`    | Provisões (novo formato) | provisions_new | NEW chart only. |
| `2.05`    | Passivos Fiscais (novo formato) | tax_liabilities_new | NEW chart only. |
| `2.06`    | Outros Passivos (novo formato) | other_liabilities_new | NEW chart only. |
| `2.07`    | Passivos s/ Ativos Não Correntes (novo) | non_current_new | NEW chart only. |
| `2.08`    | Patrimônio Líquido (novo formato) | equity_new | NEW chart only (PL moves here when 2.03 becomes amortized-cost debt). |

## grupo filter (BPP vs BPA distinction)

DFP stores the BPP `grupo` value as:

| grupo | Statement |
|-------|-----------|
| `DF Consolidado - Balanço Patrimonial Passivo` | **BPP** (this mode — liabilities + equity side) |
| `DF Consolidado - Balanço Patrimonial Ativo` | **BPA** — assets side; DIFFERENT statement |
| `DF Individual - Balanço Patrimonial Passivo` | **BPP** (individual) |
| `DF Individual - Balanço Patrimonial Ativo` | **BPA** (individual) |

The standalone BPP mode filters by `grupo LIKE '%Patrimonial Passivo%'`.
This matches BPP only — `'%Patrimonial Ativo%'` would return BPA rows.
Since codes `2.xx` are unique to BPP (BPA uses `1.xx`), the code-list
filter (`codigo IN (...)`) is sufficient on its own — but the grupo filter
is included as a safety net for future CVM schema changes.

## How the financials skill uses these codes

### `mode="bpp"` (v1.10, standalone)

Surfaces ALL 17 codes above, with `label` + `section` + `valor_brl` per
period. Filters `grupo LIKE '%Patrimonial Passivo%'`. Supports both annual
(DFP, `meses=12`) and quarterly (ITR `meses=3/6/9` + DFP `meses=12`).

### `SUMMARY_CODES` (annual / quarterly / summary / dashboard)

The summary modes use a curated subset of the BPP codes for ratio
computation. After v1.10 the SUMMARY_CODES for BPP are:

| Code | Metric key in `_extract_metrics` |
|------|----------------------------------|
| `2` | (in SUMMARY_CODES via RESUMO_ACCOUNTS — for rendering only) |
| `2.01.01` | `fornecedores` (NEW v1.10) |
| `2.01.04` | (in SUMMARY_CODES via financials extras — for `divida_bruta` derivation) |
| `2.02.01` | (in SUMMARY_CODES via financials extras — for `divida_bruta` derivation) |
| `2.03` | `patrimonio_liquido` |
| `2.03.01` | `capital_social` (NEW v1.10) |
| `2.03.02` | `reservas_capital` (NEW v1.10) |
| `2.03.04` | `reservas_lucros` (NEW v1.10) |
| `2.03.05` | `lucros_acumulados` (NEW v1.10) |
| `2.03.09` | `minority_interest` (NEW v1.10) |

### `complete` mode

`KEY_CODES_BY_GRUPO["BPP"]` (after v1.10): the full 17-code list above
(covering BOTH old and new chart formats — a filer that uses the new
`2.08` for PL will populate that row; a filer that uses the old `2.03`
for PL will populate that).

## Impact on existing engines

### `patrimonio_liquido` engine (uses `2.03`)

The pl engine queries `2.03` and gets whatever the filer uses:

- **95% of filers (6352/6681 rows)**: `2.03` = "Patrimônio Líquido" (PL) ✓
- **5% of filers (NEW chart)**: `2.03` = "Passivos Financeiros ao Custo
  Amortizado" (DEBT, not PL!) — engine would return debt instead of equity.

For the 95% majority, the pl engine works correctly. For the 5% minority,
the result is wrong but silent — no error raised. Callers needing precise
semantics should check whether `2.08` exists (NEW chart) and read PL from
there instead. A future engine hardening could add a `descricao`-search
fallback similar to what the EBIT engine does for `3.05` (description-search
fallback for banks).

### `fornecedores` / payables engine (uses `2.01.01`)

The payables engine queries `2.01.01` and gets whatever the filer uses:

- **~95% of filers (6317/6476 rows)**: `2.01.01` = "Obrigações Sociais e
  Trabalhistas" (labor obligations) — not strictly "trade payables" despite
  the engine's `fornecedores` key name
- **~5% of filers**: `2.01.01` = "Fornecedores" / "Contas a Pagar" /
  "Depósitos" (trade payables or deposits)

The engine name `fornecedores` is the canonical "trade payables" concept
but in practice returns whatever payables-like obligation the filer puts
at `2.01.01`. This matches the CVM chart drift pattern (same as BPA's
`1.01` = "Ativo Circulante" vs "Caixa e Equivalentes"). Documented as a
data correctness issue, not a code bug.

## Common pitfalls

1. **`2.03` means different things in old vs new charts.** Older filers
   use it for "Patrimônio Líquido" (PL — equity). Newer filers use it for
   "Passivos Financeiros ao Custo Amortizado" (DEBT). The engines query by
   `codigo` only — they return whatever `2.03` is for that filer. This is
   a data correctness issue, not a code bug. Callers needing precise
   semantics should filter by `descricao` as well, or check whether `2.08`
   exists (NEW chart only — PL moved there).

2. **`2.01.01` is a "grab bag" of payables concepts.** Most filers use it
   for "Obrigações Sociais e Trabalhistas" (labor obligations, 6317 rows),
   not "Fornecedores" (trade payables). The `fornecedores` engine key name
   is the canonical trade-payables concept but in practice returns whatever
   the filer puts at `2.01.01`. Same chart drift pattern as BPA's `1.01`.

3. **95% of filers still use the OLD chart (PL at `2.03`).** The pl engine
   works correctly for the majority — 6352 of 6681 rows. The 5% on the NEW
   chart get debt instead of equity from the engine, silently. No fix is
   planned at the engine level (would break the 95% majority); instead,
   the standalone `bpp` mode (v1.10) surfaces both `2.03` and `2.08` so
   callers can disambiguate which chart the filer uses.

4. **Codes `2.04`–`2.07` exist only in the NEW chart.** Old-chart filers
   don't populate these rows. A caller checking `if "2.08" in accounts`
   can detect the NEW chart; `if "2.04" in accounts` similarly.

5. **BPP is available in BOTH DFP and ITR.** Annual BPP comes from DFP
   (`meses=12`). Quarterly cumulative BPP comes from ITR (`meses=3/6/9`).
   The `bpp` mode with `quarterly=1` queries both. Snapshots (BPP) use
   the period-end value directly — no subtraction needed (unlike flow
   statements DRE/DFC/DVA where Q2 = cum6 − cum3).

6. **BPP is NOT BPA.** `grupo LIKE '%Patrimonial Ativo%'` returns the
   assets side (BPA), which is a separate statement. Don't confuse the
   two filters — BPP mode uses `'%Patrimonial Passivo%'`.

---

*Last updated: 2026-07-30 (v1.10 — created alongside the standalone `bpp` mode + BPP sub-codes added to SUMMARY_CODES).*
