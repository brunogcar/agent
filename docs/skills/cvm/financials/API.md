<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 📖 API Reference

## skill(domain="cvm", sub_domain="financials", ...)

### mode="quarterly" (default)

Standalone quarterly summary + ratios. Derives Q1-Q4 from ITR cumulative + DFP annual.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | B3 ticker (PETR4), name, or CNPJ. Required |
| periods | int | 8 | Number of quarters |
| consolidado | int | 1 | 1=consolidated, 0=individual |

```json
{
  "status": "ok",
  "company": "PETROLEO BRASILEIRO S.A.",
  "period_type": "quarterly",
  "periods": [
    {
      "period": "1T2026",
      "year": 2026,
      "quarter": 1,
      "metrics": {
        "ativo_total": 18159922000,
        "receita_liquida": 537661000,
        "ebitda": 508485000,
        "lucro_liquido": 371553000,
        ...
      },
      "ratios": {
        "marg_bruta": 0.609,
        "marg_ebitda": 0.946,
        "roa": 0.105,
        "roe": 0.255,
        ...
      }
    }
  ]
}
```

### mode="annual"

Annual summary + ratios from DFP.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| periods | int | 5 | Number of years |
| consolidado | int | 1 | 1=consolidated, 0=individual |

### mode="complete"

Full statements by grupo + key account codes (not all 497).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| period | str | "quarterly" | "quarterly" or "annual" |
| grupo | str | "" | Filter: BPA, BPP, DRE, DFC_MI, DVA. Empty = all key codes |
| consolidado | int | 1 | 1=consolidated, 0=individual |
| periods | int | 8 | Quarters (quarterly) or years (annual) |

### mode="summary"

Combined: latest annual + latest quarterly (4Q trend) + key ratios. Best-effort.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| consolidado | int | 1 | 1=consolidated, 0=individual |

**v1.3 response:**
```json
{
  "status": "ok",
  "company": "PETR4",
  "sections": {
    "latest_annual":   { /* same as annual(periods=1).periods[0] */ },
    "latest_quarterly": { /* same as quarterly(periods=4).periods[-1] */ },
    "quarterly_trend":  [ /* quarterly(periods=4).periods, oldest-first */ ],
    "current_ratios": {
      "date": "2026-07-27",
      "roic":          0.18,
      "graham_number": 75.0,
      "ev_ebitda":     6.4,
      "p_fcf":         10.0,
      "p_ebit":        7.2,
      "p_fco":         2.8
    }
  }
}
```

`current_ratios` is computed by delegating to `skills.cvm.calculations.metrics.*` at today's date (point-in-time). Each metric is wrapped in `_safe_call` so a missing DB (e.g. `cotahist.db` for price-based ratios) returns `None` instead of crashing the whole summary. Fundamental ratios (ROIC, Graham) typically populate from DFP/ITR alone; price-based ratios (EV/EBITDA, P/FCF, P/EBIT, P/FCO) additionally require `b3/cotahist.db` + `cvm/fre.db`.

### mode="bpa" (v1.9)
Balanço Patrimonial Ativo (Balance Sheet — Assets) for the last N periods.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |
| `periods` | `int` | `5` | Number of periods to return |
| `consolidado` | `int` | `1` | 1=consolidated, 0=individual |
| `quarterly` | `int` | `0` | 1=quarterly (ITR+DFP), 0=annual only (DFP) |

Returns: `{status, company, period_type, periods: [{data_fim_exerc, meses, accounts: {codigo: {label, section, valor_brl}}}]}`

The BPA is structured top-to-bottom (Total → Circulante → Cash → Investments → Receivables → Inventories → Não Circulante → PP&E → Intangibles), 16 codes:

| Code | Label (canonical) | Section |
|------|-------------------|---------|
| `1` | Ativo Total | `total` |
| `1.01` | Ativo Circulante | `current` |
| `1.01.01` | Caixa e Equivalentes | `cash` |
| `1.01.02` | Aplicações Financeiras | `investments_short` |
| `1.01.03` | Contas a Receber | `receivables` (NEW v1.9) |
| `1.01.04` | Estoques | `inventory` (NEW v1.9) |
| `1.02` | Ativo Não Circulante | `non_current` |
| `1.02.01` | Ativo Não Circulante (sub) | `non_current_sub` |
| `1.02.03` | Imobilizado | `ppe` (NEW v1.9) |
| `1.02.04` | Intangível | `intangibles` (NEW v1.9) |
| `1.03`–`1.06` | (varies — multiple descriptions per code) | `other_1`–`other_4` |
| `1.07` | Imobilizado (novo formato) | `ppe_new` |
| `1.08` | Intangível (novo formato) | `intangibles_new` |

The `grupo` filter is `LIKE '%Patrimonial Ativo%'` — this matches BPA
rows from both consolidated and individual filings, and EXCLUDES the
separate "Patrimonial Passivo" (BPP) statement. See
[DFP Architecture → architecture/BPA.md](../../data_sources/cvm/dfp/architecture/BPA.md)
for the old-vs-new chart drift (codes 1.01, 1.02, 1.02.03, 1.02.04 have
DIFFERENT meanings in old vs new CVM charts — engines query by codigo
only, so callers needing precise semantics should filter by `descricao`).

[v1.9] `SUMMARY_CODES` now also includes the 4 BPA asset sub-codes
(`1.01.03`, `1.01.04`, `1.02.03`, `1.02.04`). `_extract_metrics` exposes
them as `contas_a_receber`, `estoques`, `imobilizado`, `intangivel` in
the per-period `metrics` dict.

[v1.9] `_extract_metrics` also exposes the 3 previously-missing DRE codes
that were in `SUMMARY_CODES` but never extracted: `custo_mercadorias`
(`3.02`), `despesas_operacionais` (`3.04`), `imposto_renda` (`3.08`).

[v1.9] `KEY_CODES_BY_GRUPO["BPA"]` expanded from 6 codes to 16 codes
(covering both OLD and NEW CVM chart formats).

### mode="dva" (v1.7)
Demonstração do Valor Adicionado (Value Added Statement) for the last N periods.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |
| `periods` | `int` | `5` | Number of periods to return |
| `consolidado` | `int` | `1` | 1=consolidated, 0=individual |
| `quarterly` | `int` | `0` | 1=quarterly (ITR+DFP), 0=annual only (DFP) |

Returns: `{status, company, period_type, periods: [{data_fim_exerc, meses, accounts: {codigo: {label, section, valor_brl}}}]}`

The DVA is structured in 2 sections:
- **Generation side** (codes 1-7): Receitas, Insumos, Valor Adicionado Bruto, Retenções, Valor Adicionado Líquido, VA Recebido, Total a Distribuir
- **Distribution side** (codes 8.1-8.4): Pessoal, Impostos, Remuneração Capital de Terceiros, Remuneração Capital Próprio

[v1.7] annual/quarterly modes now also include 5 DVA metrics in the `metrics` dict:
`dva_total`, `dva_pessoal`, `dva_impostos`, `dva_remu_capital_terceiros`, `dva_remu_capital_proprio`.

[v1.7] `complete` mode DVA section expanded from 3 proventos codes to full 15-code statement.

### mode="dre" (v1.8)
Demonstração do Resultado do Exercício (Income Statement) for the last N periods.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |
| `periods` | `int` | `5` | Number of periods to return |
| `consolidado` | `int` | `1` | 1=consolidated, 0=individual |
| `quarterly` | `int` | `0` | 1=quarterly (ITR+DFP), 0=annual only (DFP) |

Returns: `{status, company, period_type, periods: [{data_fim_exerc, meses, accounts: {codigo: {label, section, valor_brl}}}]}`

The DRE is structured top-to-bottom, 10 codes covering the income statement:

| Code | Label (canonical) | Section |
|------|-------------------|---------|
| `3.01` | Receita Líquida de Vendas e/ou Serviços | `revenue` |
| `3.02` | Custo dos Bens e/ou Serviços Vendidos | `costs` |
| `3.03` | Resultado Bruto | `gross_profit` |
| `3.04` | Despesas Administrativas, Gerais e Comerciais | `operating_expenses` |
| `3.05` | Resultado Antes do Resultado Financeiro e dos Tributos | `ebit` |
| `3.06` | Resultado Financeiro | `financial_result` |
| `3.07` | Resultado Líquido das Operações Continuadas | `net_continuing` (NEW v1.8) |
| `3.08` | Imposto de Renda e Contribuição Social sobre o Lucro | `tax` |
| `3.09` | Lucro/Prejuízo Consolidado do Período | `net_income` |
| `3.11` | Lucro/Prejuízo Consolidado do Período (alt) | `net_income_alt` |

The `grupo` filter is `LIKE '%Demonstração do Resultado%'` — this matches DRE
rows from both consolidated and individual filings, and EXCLUDES the separate
"Demonstração de Resultado Abrangente" (DRA) statement. See
[DFP Architecture → architecture/DRE.md](../../data_sources/cvm/dfp/architecture/DRE.md) for the
multiple-labels-per-code quirks (CVM chart drift over filing years).

[v1.8] `SUMMARY_CODES` now also includes `3.07` (Resultado Líquido das
Operações Continuadas). `_extract_metrics` exposes it as
`resultado_liquido_continuadas` in the per-period `metrics` dict.

---

## Examples

```
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="annual", params='{"company":"VALE3","periods":10}')
skill(domain="cvm", sub_domain="financials", mode="complete", params='{"company":"PETR4","grupo":"DRE"}')
skill(domain="cvm", sub_domain="financials", mode="summary", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="bpa", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="bpa", params='{"company":"PETR4","quarterly":1,"periods":8}')
skill(domain="cvm", sub_domain="financials", mode="dva", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="dva", params='{"company":"PETR4","quarterly":1,"periods":8}')
skill(domain="cvm", sub_domain="financials", mode="dre", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="dre", params='{"company":"PETR4","quarterly":1,"periods":8}')
```

---

*Last updated: 2026-07-30 (v1.9 — BPA mode + BPA sub-codes in SUMMARY_CODES + 3 missing DRE codes in `_extract_metrics`). See [ARCHITECTURE.md](ARCHITECTURE.md) for the updated source code reference.*
