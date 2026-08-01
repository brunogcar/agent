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

### mode="dashboard" (v1.12; v1.13 review fixes; v1.14 sync guard)

7-tab multi-section dashboard, optimized for the report tool's `dashboard` action.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| consolidado | int | 1 | 1=consolidated, 0=individual |
| skip_sync | bool | False | [v1.14] Bypass sync guard (no freshness check, no force-sync) |

**v1.12 tabs:**

1. **Overview** — KPI cards (Receita TTM, EBITDA, Lucro Líquido, ROE, ROIC, Dív.Líq/EBITDA) + summary text + latest-annual metrics table + quarterly trend + freshness metadata.
2. **Indicadores** — `type: "ratio_grid"` with all 7 ratio categories (Valuation / Rentabilidade / Liquidez / Endividamento / Eficiência / Crescimento / Tributos) via `compute_all_ratios()`.
3. **Crescimento** — 3M/1Y/5Y growth table (Receita, Lucro Bruto, Lucro Líquido) + bar chart comparing 1Y vs 5Y.
4. **Balanço** — `type: "subtabs"` with BPA + BPP sub-tabs (latest annual accounts, grouped by section).
5. **DRE** — latest annual accounts table + 5Y margin trend line chart (Bruta / EBIT / EBITDA / Líquida).
6. **DFC** — latest annual accounts table + 5Y stacked bar chart (FCO / FCI / FCF).
7. **DVA** — latest annual accounts table + doughnut chart of wealth distribution (Pessoal / Governo / Credores / Acionistas).

The dashboard calls the 5 standalone statement modes (bpa/bpp/dre/dfc/dva) via try/except — a failure in one statement degrades the corresponding tab to an error text section instead of crashing the whole dashboard.

**Response shape:**
```json
{
  "status": "ok",
  "company": "PETR4",
  "kpis": [
    {"label": "Receita (TTM)", "value": "R$ 500,00 B", "unit": "BRL"},
    ...
  ],
  "tabs": [
    {"name": "Overview",    "sections": [...]},
    {"name": "Indicadores", "sections": [{"type": "ratio_grid", ...}]},
    {"name": "Crescimento", "sections": [{"type": "table", ...}, {"type": "chart", ...}]},
    {"name": "Balanço",     "sections": [{"type": "subtabs", "tabs": [{"name": "BPA", ...}, {"name": "BPP", ...}]}]},
    {"name": "DRE",         "sections": [{"type": "table", ...}, {"type": "chart", ...}]},
    {"name": "DFC",         "sections": [{"type": "table", ...}, {"type": "chart", ...}]},
    {"name": "DVA",         "sections": [{"type": "table", ...}, {"type": "chart", ...}]}
  ],
  "_sync": {
    "synced": ["dfp"],
    "fresh": ["itr", "bridge"],
    "errors": [],
    "skipped": []
  }
}
```

**`_sync` field** [v1.14]: Present when sync guard is active (i.e., `skip_sync` not passed). Shows which sources were force-synced, which were already fresh, which had errors, and which were skipped (via `CVM_SKIP_SYNC=1` env var).

### mode="ttm" (v1.15)

Rolling TTM (anualizado) time series. For each historical quarter-end date, computes trailing-12-months values via calculations engines. Deseasonalizes flow metrics — 4 data points per year with quarterly noise smoothed.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| periods | int | 8 | Number of TTM periods to return |
| consolidado | int | 1 | 1=consolidated, 0=individual |

**Response shape:**
```json
{
  "status": "ok",
  "company": "PETR4",
  "periods": [
    {"period_range": "2T2023–1T2024", "ttm_date": "2024-03-31", "quarter": "1T2024", "metrics": {...}, "ratios": {...}},
    ...
  ]
}
```

### mode="yoy_quarterly" (v1.15)

Same-quarter year-over-year comparison (Trimestre). Groups standalone quarters by Q1/Q2/Q3/Q4 and compares each quarter across years. Shows YoY growth per quarter.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| years | int | 5 | Number of years to compare |
| consolidado | int | 1 | 1=consolidated, 0=individual |

**Response shape:**
```json
{
  "status": "ok",
  "company": "PETR4",
  "groups": [
    {"quarter": "Q1", "periods": [{"period": "1T2024", "year": 2024, "quarter": 1, "metrics": {...}, "ratios": {...}, "yoy_growth": {"receita_liquida": 0.15}}]},
    {"quarter": "Q2", "periods": [...]},
    {"quarter": "Q3", "periods": [...]},
    {"quarter": "Q4", "periods": [...]}
  ]
}
```

### mode="bpa" / "bpp" / "dre" / "dfc" / "dva" (v1.12)

Standalone statement modes — thin wrappers over `complete(grupo=...)` that reshape the per-period accounts list into a dict-keyed shape with `section` labels.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| period | str | "annual" | "annual" or "quarterly" |
| consolidado | int | 1 | 1=consolidated, 0=individual |
| periods | int | 1 (annual) / 4 (quarterly) | Number of periods |

**Response shape:**
```json
{
  "status": "ok",
  "company": "PETROLEO BRASILEIRO S.A.",
  "period_type": "annual",
  "statement": "DRE",
  "grupo_filter": "DRE",
  "periods": [
    {
      "data_fim_exerc": "2023-12-31",
      "meses": 12,
      "period": "2023",
      "year": 2023,
      "quarter": null,
      "accounts": {
        "3.01": {"label": "Receita Líquida", "section": "DRE", "valor_brl": 50000000000},
        "3.03": {"label": "Lucro Bruto",     "section": "DRE", "valor_brl": 20000000000},
        ...
      }
    }
  ]
}
```

The `section` field is derived from the codigo prefix:

| Mode | Section labels |
|------|----------------|
| bpa  | Ativo Total / Ativo Circulante / Ativo Não Circulante |
| bpp  | Passivo Total / Passivo Circulante / Passivo Não Circulante / Patrimônio Líquido |
| dre  | DRE (single section) |
| dfc  | Operações / Investimento / Financiamento |
| dva  | Geração (codes 1-7) / Distribuição (codes 8.*) |

Pipe any of these results into the report tool via the generic `financials_statement` adapter:

```
report(action="table", data=<bpa result>, config={"adapter": "financials_statement"})
```

---

## Examples

```
skill(domain="cvm", sub_domain="financials", mode="quarterly", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="annual", params='{"company":"VALE3","periods":10}')
skill(domain="cvm", sub_domain="financials", mode="complete", params='{"company":"PETR4","grupo":"DRE"}')
skill(domain="cvm", sub_domain="financials", mode="summary", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="dashboard", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="dre", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="financials", mode="bpa", params='{"company":"PETR4","period":"annual"}')
skill(domain="cvm", sub_domain="financials", mode="dva", params='{"company":"PETR4"}')
```

---

*Last updated: 2026-08-01 (v1.15 — sync guard + review fixes). See [CHANGELOG.md](CHANGELOG.md) for version history.*
