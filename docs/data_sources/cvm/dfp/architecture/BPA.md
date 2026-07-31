<- Back to [DFP Architecture](../ARCHITECTURE.md)

# 📊 BPA — Balanço Patrimonial Ativo (Balance Sheet — Assets)

The BPA is the Brazilian balance sheet's assets side. CVM assigns codes in
the `1.xx` range. All 16 engine codes verified to exist in real DFP data
(rows range from 6377 to 6685).

## ⚠️ The chart drift trap (OLD vs NEW chart)

The CVM BPA chart of accounts has **CHANGED over the years**. Codes `1.01`,
`1.02`, `1.02.03`, `1.02.04` exist in BOTH the old chart and the new chart
but **have DIFFERENT meanings** in each.

| Code | OLD chart label (pre-reform filers) | NEW chart label (post-reform filers) |
|------|-------------------------------------|--------------------------------------|
| `1.01` | Ativo Circulante | Caixa e Equivalentes |
| `1.02` | Ativo Não Circulante | Aplicações Financeiras |
| `1.02.03` | Imobilizado | (not used — moved to `1.07`) |
| `1.02.04` | Intangível | (not used — moved to `1.08`) |
| `1.07` | (not used in OLD chart) | Imobilizado (replaces `1.02.03`) |
| `1.08` | (not used in OLD chart) | Intangível (replaces `1.02.04`) |

The engines query by `codigo` only — there is no `grupo` disambiguation
because codes `1.xx` are **unique to BPA** (BPP uses `2.xx`, DRE uses `3.xx`).
As a result, the engines return whatever `1.01` happens to be for that
filer — which may be "Ativo Circulante" (old) or "Caixa e Equivalentes"
(new). This is a **data correctness issue, not a code bug**: callers needing
precise semantics should filter by `descricao` as well.

The standalone `bpa` mode (v1.9) surfaces the raw value with the canonical
label from the codes table; the per-row `descricao` from DFP is preserved
in the underlying row but the mode returns the canonical label.

## Chart of accounts (16 codes, v1.9+)

| Code | Canonical label | Section | Notes |
|------|-----------------|---------|-------|
| `1`       | Ativo Total | total | 6685 rows. Grand total assets. |
| `1.01`    | Ativo Circulante | current | 6685 rows. ⚠️ NEW chart = "Caixa e Equivalentes" (chart drift). |
| `1.01.01` | Caixa e Equivalentes | cash | 6536 rows. |
| `1.01.02` | Aplicações Financeiras | investments_short | 6483 rows. Short-term financial investments. |
| `1.01.03` | Contas a Receber | receivables | 6389 rows. [v1.9] Added to SUMMARY_CODES + `_extract_metrics`. |
| `1.01.04` | Estoques | inventory | 6377 rows. [v1.9] Added to SUMMARY_CODES + `_extract_metrics`. |
| `1.02`    | Ativo Não Circulante | non_current | 6685 rows. ⚠️ NEW chart = "Aplicações Financeiras" (chart drift). |
| `1.02.01` | Ativo Não Circulante (sub) | non_current_sub | 6685 rows. Sub-line of non-current assets. |
| `1.02.03` | Imobilizado | ppe | 6505 rows. OLD chart only (NEW uses `1.07`). [v1.9] Added to SUMMARY_CODES + `_extract_metrics`. |
| `1.02.04` | Intangível | intangibles | 6430 rows. OLD chart only (NEW uses `1.08`). [v1.9] Added to SUMMARY_CODES + `_extract_metrics`. |
| `1.03`    | Empréstimos e Recebíveis / Tributos | other_1 | Multiple descriptions per code (chart drift). |
| `1.04`    | Tributos Diferidos / Outros Ativos | other_2 | Multiple descriptions per code (chart drift). |
| `1.05`    | Outros Ativos / Investimentos | other_3 | Multiple descriptions per code (chart drift). |
| `1.06`    | Investimentos / Imobilizado | other_4 | Multiple descriptions per code (chart drift). |
| `1.07`    | Imobilizado (novo formato) | ppe_new | NEW chart only (replaces `1.02.03`). |
| `1.08`    | Intangível (novo formato) | intangibles_new | NEW chart only (replaces `1.02.04`). |

## grupo filter (BPA vs BPP distinction)

DFP stores the BPA `grupo` value as:

| grupo | Statement |
|-------|-----------|
| `DF Consolidado - Balanço Patrimonial Ativo` | **BPA** (this mode — assets side) |
| `DF Consolidado - Balanço Patrimonial Passivo` | **BPP** — liabilities + equity side; DIFFERENT statement |
| `DF Individual - Balanço Patrimonial Ativo` | **BPA** (individual) |
| `DF Individual - Balanço Patrimonial Passivo` | **BPP** (individual) |

The standalone BPA mode filters by `grupo LIKE '%Patrimonial Ativo%'`.
This matches BPA only — `'%Patrimonial Passivo%'` would return BPP rows.
Since codes `1.xx` are unique to BPA (BPP uses `2.xx`), the code-list
filter (`codigo IN (...)`) is sufficient on its own — but the grupo filter
is included as a safety net for future CVM schema changes.

## How the financials skill uses these codes

### `mode="bpa"` (v1.9, standalone)

Surfaces ALL 16 codes above, with `label` + `section` + `valor_brl` per
period. Filters `grupo LIKE '%Patrimonial Ativo%'`. Supports both annual
(DFP, `meses=12`) and quarterly (ITR `meses=3/6/9` + DFP `meses=12`).

### `SUMMARY_CODES` (annual / quarterly / summary / dashboard)

The summary modes use a curated subset of the BPA codes for ratio
computation. After v1.9 the SUMMARY_CODES for BPA are:

| Code | Metric key in `_extract_metrics` |
|------|----------------------------------|
| `1` | `ativo_total` |
| `1.01` | (in SUMMARY_CODES via RESUMO_ACCOUNTS — for rendering only) |
| `1.01.01` | `caixa` |
| `1.01.03` | `contas_a_receber` (NEW v1.9) |
| `1.01.04` | `estoques` (NEW v1.9) |
| `1.02` | (in SUMMARY_CODES via RESUMO_ACCOUNTS — for rendering only) |
| `1.02.01` | (in SUMMARY_CODES via RESUMO_ACCOUNTS — for rendering only) |
| `1.02.03` | `imobilizado` (NEW v1.9) |
| `1.02.04` | `intangivel` (NEW v1.9) |

### `complete` mode

`KEY_CODES_BY_GRUPO["BPA"]` (after v1.9): the full 16-code list above
(covering BOTH old and new chart formats — a filer that uses the new
`1.07` / `1.08` will populate those rows; a filer that uses the old
`1.02.03` / `1.02.04` will populate those).

## Common pitfalls

1. **`1.01` means different things in old vs new charts.** Older filers
   use it for "Ativo Circulante" (Current Assets), newer filers use it
   for "Caixa e Equivalentes" (Cash & Equivalents). The engines query by
   `codigo` only — they return whatever `1.01` is for that filer. This is
   a data correctness issue, not a code bug. Callers needing precise
   semantics should filter by `descricao` as well.

2. **`1.02.03` (Imobilizado, OLD) vs `1.07` (Imobilizado, NEW).** The
   same concept (PP&E) sits at different codes depending on which CVM
   chart the filer adopted. The `bpa` mode surfaces BOTH codes so the
   caller sees whichever the filer uses. The `ppe` section label vs the
   `ppe_new` section label disambiguates which chart was used.

3. **`1.02.04` (Intangível, OLD) vs `1.08` (Intangível, NEW).** Same
   issue as #2 but for intangibles. Surfaces both codes; `intangibles`
   vs `intangibles_new` section labels disambiguate.

4. **Codes `1.03`–`1.06` have multiple descriptions per code.** Each
   appears in real DFP data with at least two different descriptions
   (e.g. `1.03` = "Empréstimos e Recebíveis" for some filers and
   "Tributos Diferidos" for others). The chart drift here is real and
   not fully documented by CVM — these codes are surfaced in `complete`
   mode but not in the SUMMARY_CODES ratio computation (their semantics
   are too inconsistent across filers).

5. **BPA is available in BOTH DFP and ITR.** Annual BPA comes from DFP
   (`meses=12`). Quarterly cumulative BPA comes from ITR (`meses=3/6/9`).
   The `bpa` mode with `quarterly=1` queries both. Snapshots (BPA) use
   the period-end value directly — no subtraction needed (unlike flow
   statements DRE/DFC/DVA where Q2 = cum6 − cum3).

6. **BPA is NOT BPP.** `grupo LIKE '%Patrimonial Passivo%'` returns the
   liabilities + equity side (BPP), which is a separate statement. Don't
   confuse the two filters — BPA mode uses `'%Patrimonial Ativo%'`.

---

*Last updated: 2026-07-30 (v1.9 — created alongside the standalone `bpa` mode + BPA sub-codes added to SUMMARY_CODES).*
