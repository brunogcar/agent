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

### mode="dashboard" (v1.12; v1.13 review fixes; v1.14 sync guard; v1.15 TTM+YoY; v1.16 dashboard v3; v1.17 single-fetch; v1.22 radar/heatmap; v1.23 price overlay + multi-period tables + trend charts; v1.24 quarterly tables + period toggle; v1.25 ALL charts toggle + cache fix; v2.0 report/ package split; v2.3 comprehensive tables + unified charts + Overview subtabs + Trimestral QoQ rename; v2.4 Trajetória Anual revamp + Red Flags collapsible fix + Quarterly Trend delta direction + real CapEx engine + F16 Quality of Earnings)

11-tab multi-section dashboard with sidebar grouping, optimized for the report tool's `dashboard` action.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| company | str | — | Required |
| consolidado | int | 1 | 1=consolidated, 0=individual |
| skip_sync | bool | False | [v1.14] Bypass sync guard (no freshness check, no force-sync) |

**v1.16 tabs (grouped into 4 sidebar sections):**

**Resumo:**
1. **Overview** — KPI cards (Receita TTM, EBITDA, Lucro Líquido, ROE, ROIC, Dív.Líq/EBITDA) + summary text + latest-annual metrics table + quarterly trend + freshness metadata + [v1.16] annual trend line chart + [v1.22] radar chart (6-axis: Rentabilidade/Crescimento/Liquidez/Alavancagem/Margem/Eficiência) + [v1.22] heatmap table (10 metrics, color-coded) + [v1.23] price overlay on trend chart (dual Y-axis) + [v1.21] WACC/DuPont/Altman Z sections.
2. **Indicadores** — `type: "subtabs"` with "Todas" + 7 category sub-tabs. Each ratio_grid item has a [v1.16] tooltip (ⓘ icon) with the formula/explanation. [v1.25] Valuation subtab split into 3 charts (EV/P/Valor); Crescimento moved to Crescimento tab.
3. **Crescimento** — 3M/1Y/5Y growth table (3M now computed from quarterly QoQ) + bar chart with 3M/1Y/5Y datasets + chart title/description. [v1.20] Now 3 separate charts (Receita / Lucro Líquido / Resultado Bruto).

**Demonstrações:**
4. **Balanço** — `type: "subtabs"` with Completo / BPA / BPP sub-tabs. [v1.22] 6 stacked-bar charts (absolute + percentage for Completo/BPA/BPP). [v1.24] Each subtab wrapped in `period_toggle` (annual + quarterly tables). [v1.25] The 6 stacked-bar charts ALSO inside the period_toggle.
5. **DRE** — [v1.23] multi-column annual table (4 years side-by-side) + [v1.24] `period_toggle` with annual + quarterly tables + [v1.23] trend chart with price overlay + [v1.25] margins chart + absolute-values chart (ALL inside the period_toggle).
6. **DFC** — [v1.23] multi-column table + trend chart with price overlay + [v1.25] stacked-bar chart + FCO-vs-Lucro-Líquido chart (ALL inside the period_toggle) + [v1.20] DFC quality section (FCF_true + Cash Conversion Ratio) outside the toggle (point-in-time).
7. **DVA** — [v1.23] multi-column table + trend chart with price overlay + [v1.18] doughnut chart with both DVA taxonomies (7.08.01-05 new + 8.01-04 old) + [v1.20] generation-side bar chart + [v1.20] dividend sustainability section (point-in-time, OUTSIDE the toggle).

**Períodos:**
8. **Anual** — raw annual periods table (6 periods) + [v1.16] multi-line trend chart.
9. **Trimestral** — raw quarterly periods table (8 periods) + [v1.16] bar chart.

**Séries Temporais:**
10. **Anualizado** — TTM (trailing 12 months) series table + line chart with title/description. [v1.25] Now 20 periods (was 8).
11. **Trimestral YoY** — [v1.16 restructured] same-quarter YoY comparison table grouped by YEAR (was by quarter) + bar chart with title/description.

The dashboard calls the 5 standalone statement modes (bpa/bpp/dre/dfc/dva) via try/except — a failure in one statement degrades the corresponding tab to an error text section instead of crashing the whole dashboard. [v1.17] All 5 statements fetched in ONE SQL query via `_fetch_all_statements_annual()`. [v1.24] Quarterly variants fetched via `_fetch_all_statements_quarterly()` (ITR+DFP for ALL KEY_CODES, BPA/BPP snapshot carry-forward, up to 20 quarterly periods).

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

*Last updated: 2026-08-13 (v2.0 — report/ package split + v1.17 single-fetch + v1.22 radar/heatmap + v1.23 price overlay + v1.24 quarterly tables + period toggle + v1.25 ALL charts toggle + cache fix). See [CHANGELOG.md](CHANGELOG.md) for version history.*
