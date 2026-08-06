<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 📝 API Reference

This doc covers historical-specific **modes** + **report adapters** + **error cases**. For engine function signatures, metric function signatures, and the registry API (`EngineSpec`, `MetricSpec`, `register_*`, `resolve_metric`, `list_*`), see [calculations/API.md](../calculations/API.md) — those are owned by the calculations package.

## 🔧 Modes

The `<metric>_history` modes are auto-generated from the metric registry. When a new metric is registered, its `<metric>_history` mode appears here automatically. The generic modes (`ratio_history`, `summary`) are static and work with any registered metric.

### `mode="lpa_history"` (auto-generated)
Daily LPA + P/L time series for the last N months.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `months` | `int` | `60` | Number of months of history (60 = 5 years) |

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "lpa",
  "per_share_label": "LPA",
  "ratio_label": "P/L",
  "date_from": "2019-07-26",
  "date_to": "2024-07-26",
  "total_days": 1200,
  "pe_days": 1100,
  "series": [
    {"date": "2019-07-26", "price": 28.5, "ttm_earnings": 100e9, "shares": 13e9, "lpa": 7.69, "pe": 3.7},
    ...
  ],
  "data_freshness": {...}
}
```

### `mode="vpa_history"` (auto-generated)
Daily VPA + P/VPA time series for the last N months.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `months` | `int` | `60` | Number of months of history (60 = 5 years) |

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "vpa",
  "per_share_label": "VPA",
  "ratio_label": "P/VPA",
  "date_from": "2019-07-26",
  "date_to": "2024-07-26",
  "total_days": 1200,
  "pvpa_days": 1100,
  "series": [
    {"date": "2019-07-26", "price": 28.5, "pl": 290e9, "shares": 13e9, "vpa": 22.31, "pvpa": 1.27},
    ...
  ],
  "data_freshness": {...}
}
```

### `mode="dpa_history"` (auto-generated)
Daily DPA + Dividend Yield + Payout time series for the last N months.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `months` | `int` | `60` | Number of months of history (60 = 5 years) |

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "dpa",
  "per_share_label": "DPA",
  "ratio_label": "Div Yield",
  "date_from": "2019-07-26",
  "date_to": "2024-07-26",
  "total_days": 1200,
  "dy_days": 1100,
  "series": [
    {"date": "2019-07-26", "price": 28.5, "dpa": 1.50, "dy": 0.053, "payout": 0.19,
     "ttm_earnings": 100e9, "shares": 13e9, "lpa": 7.69},
    ...
  ],
  "data_freshness": {...}
}
```

**Field meanings:**
- `dpa`: Dividends Per Share, TTM (R$/share) — per-share value
- `dy`: Dividend Yield = DPA / price (fraction, e.g., 0.053 = 5.3%) — price ratio
- `payout`: Payout = DPA / LPA (fraction, e.g., 0.19 = 19%) — bonus ratio
- `lpa`: LPA = TTM earnings / shares (needed for payout)

**Special values:**
- `dpa: null` → no dividends data available
- `dpa: 0.0` → company exists but pays no dividends (valid, dy = 0.0)
- `payout: null` → LPA <= 0 (negative earnings — payout meaningless) or DPA is None

### `mode="rps_history"` (auto-generated)
Daily RPS + PSR time series for the last N months.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `months` | `int` | `60` | Number of months of history (60 = 5 years) |

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "rps",
  "per_share_label": "RPS",
  "ratio_label": "PSR",
  "date_from": "2019-07-26",
  "date_to": "2024-07-26",
  "total_days": 1200,
  "psr_days": 1100,
  "series": [
    {"date": "2019-07-26", "price": 28.5, "ttm_rev": 250e9, "shares": 13e9, "rps": 19.23, "psr": 1.48},
    ...
  ],
  "data_freshness": {...}
}
```

### `mode="roe_history"` (auto-generated)
Daily ROE time series. ROE is a fundamental ratio (no price, no shares).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `months` | `int` | `60` | Number of months of history (60 = 5 years) |

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "roe",
  "per_share_label": null,
  "ratio_label": "ROE",
  "date_from": "2019-07-26",
  "date_to": "2024-07-26",
  "total_days": 20,
  "roe_days": 18,
  "series": [
    {"date": "2024-03-31", "roe": 0.34, "ttm_earnings": 120e9, "pl": 350e9},
    ...
  ],
  "data_freshness": {...}
}
```

**Note:** ROE series has ~4-8 data points per year (quarterly earnings + PL snapshots), not daily. No `price` or `shares` in series entries.

### `mode="ratio_history"` (generic)
Any metric over time. Accepts canonical names and aliases.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `lpa` | Metric name or alias (see table below) |
| `months` | `int` | `60` | Number of months |

**Metric names + aliases:**

The metrics + aliases table is owned by calculations — see [calculations/API.md](../calculations/API.md#metric-names--aliases-complete-table) for the canonical table. Reproduced here for convenience:

| Canonical | Aliases (EN) | Aliases (PT) | Per-share | Ratio | Bonus |
|---|---|---|---|---|---|
| `lpa` | `pe`, `pl`, `p/l` | `preco_lucro` | LPA (earnings/shares) | P/L (price/LPA) | — |
| `vpa` | `pvpa`, `p/vpa` | `preco_vpa`, `p_vpa` | VPA (pl/shares) | P/VPA (price/VPA) | — |
| `dpa` | `dy`, `dividend_yield`, `yld`, `payout` | `rendimento`, `rendimento_dividendo`, `div_yield` | DPA (dividends TTM) | Div Yield (DPA/price) | Payout (DPA/LPA) |
| `rps` | `psr`, `p/sr`, `price_sales` | `preco_venda`, `p_venda` | RPS (revenue/shares) | PSR (price/RPS) | — |
| `roe` | `return_on_equity` | `retorno_pl`, `retorno_patrimonio` | — (fundamental) | ROE (earnings/PL) | — |
| `roa` | `return_on_assets` | `retorno_ativos` | — (fundamental) | ROA (earnings/assets) | — |
| `gross_margin` | `gm`, `gross_margin_pct` | `margem_bruta` | — (fundamental) | Margem Bruta (gross_profit/revenue) | — |
| `operating_margin` | `om`, `operating_margin_pct` | `margem_operacional` | — (fundamental) | Margem Operacional (EBIT/revenue) | — |
| `roic` | `return_on_invested_capital` | `retorno_capital_investido` | — (fundamental) | ROIC (NOPAT/invested_capital) | — |
| `ev_ebitda` | `ev_ebit`, `evebitda`, `eva_ebitda` | — | EBITDA/Ação (EBIT+D&A)/shares | EV/EBITDA (EV/EBITDA) | — |
| `net_margin` | `nm`, `net_margin_pct` | `margem_liquida`, `ml` | — (fundamental) | Margem Líquida (earnings/revenue) | — |
| `ebitda_margin` | `em`, `ebitda_margin_pct` | `margem_ebitda` | — (fundamental) | Margem EBITDA (EBIT+D&A)/revenue | — |
| `debt_equity` | `de` | `divida_pl`, `divida_patrimonio` | — (fundamental) | Dívida/PL (debt/PL) | — |
| `net_debt_ebitda` | `nde`, `net_debt_to_ebitda` | `dl_ebitda`, `divida_liquida_ebitda` | — (fundamental) | DL/EBITDA ((debt-cash)/EBITDA) | — |
| `asset_turnover` | `at`, `asset_turnover_ratio` | `giro_ativos` | — (fundamental) | Giro de Ativos (revenue/assets) | — |
| `capex_revenue` | `capex_intensity` | `intensidade_capex` | — (fundamental) | CapEx/Receita (capex/revenue) | — |
| `current_ratio` | `cr`, `current_liquidity` | `liquidez_corrente` | — (fundamental) | Liquidez Corrente (current_assets/current_liabilities) | — |

**Error cases:**
- Missing company → `{"status": "error", "error": "company is required"}`
- Unknown metric → `{"status": "error", "error": "Unknown metric '<name>'. Available: ['dpa', 'lpa', 'roe', 'rps', 'vpa']"}`

### `mode="summary"` (generic, metric-aware)
Current ratio vs 1Y/3Y/5Y average + min/max/percentile. Includes BOTH per-share value and ratio in the result.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `lpa` | Metric name or alias |
| `months` | `int` | `60` | History window for percentile (always uses max(months, 60)) |

Returns (metric=lpa):
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "lpa",
  "per_share_label": "LPA",
  "ratio_label": "P/L",
  "current": {
    "date": "2024-07-26",
    "lpa": 10.35,
    "pe": 4.75,
    "price": 38.5,
    "ttm_earnings": 134e9,
    "shares": 13e9
  },
  "averages": {"1y": 6.2, "3y": 7.5, "5y": 8.1},
  "range": {"min": 3.1, "max": 12.5},
  "percentile": 25.0,
  "interpretation": "cheap (below 25th percentile of history)",
  "data_points": 1100,
  "date_range": {"from": "2019-07-26", "to": "2024-07-26"},
  "data_freshness": {...}
}
```

Returns (metric=vpa):
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "vpa",
  "per_share_label": "VPA",
  "ratio_label": "P/VPA",
  "current": {
    "date": "2024-07-26",
    "vpa": 23.85,
    "pvpa": 1.45,
    "price": 38.5,
    "pl": 350e9,
    "shares": 13e9
  },
  "averages": {"1y": 1.5, "3y": 1.6, "5y": 1.7},
  "range": {"min": 0.9, "max": 2.1},
  "percentile": 30.0,
  "interpretation": "fair (between 25th-75th percentile of history)",
  ...
}
```

**Interpretation thresholds (all metrics):**
| Percentile | Interpretation |
|---|---|
| ≤ 25 | cheap (below 25th percentile of history) |
| 25–75 | fair (between 25th-75th percentile of history) |
| ≥ 75 | expensive (above 75th percentile of history) |

**Error cases:**
- Missing company → `{"status": "error", "error": "company is required"}`
- Unknown metric → `{"status": "error", "error": "Unknown metric '<name>'. Available: ['lpa', 'vpa']"}`
- No price data → `{"status": "not_found", "error": "No price data for '<company>'"}`
- No valid ratio data (negative earnings/equity) → `{"status": "not_found", "error": "No valid <label> data for '<company>' (possibly negative earnings/equity)"}`

---

## 🛠️ Tool Invocation

```python
# LPA + P/L time series
skill(domain="cvm", sub_domain="historical", mode="lpa_history", params='{"company":"PETR4","months":60}')

# VPA + P/VPA time series
skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')

# Summary (default metric = lpa)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')

# Summary for vpa metric
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"vpa"}')

# Generic ratio history (accepts aliases: pe → lpa, pvpa → vpa)
skill(domain="cvm", sub_domain="historical", mode="ratio_history", params='{"company":"PETR4","metric":"pe","months":120}')
```

---

## 📊 Report Adapters

Chart adapters are auto-registered for each metric. The summary adapter is metric-aware. The dashboard adapter (v1.2) is a thin pass-through of the multi-tab `dashboard()` payload.

| Adapter | Source mode | What it renders |
|---|---|---|
| `historical_<metric>_chart` (auto-generated, one per metric) | `<metric>_history` | Dual-dataset line chart (Type 1: per-share + ratio) OR single-dataset (Type 2: fundamental ratio) |
| `historical_lpa_chart` | lpa_history | Dual-dataset line chart: LPA (per-share) + P/L (ratio) |
| `historical_vpa_chart` | vpa_history | Dual-dataset line chart: VPA (per-share) + P/VPA (ratio) |
| `historical_dpa_chart` | dpa_history | Dual-dataset line chart: DPA (per-share) + Div Yield (ratio) |
| `historical_rps_chart` | rps_history | Dual-dataset line chart: RPS (per-share) + PSR (ratio) |
| `historical_roe_chart` | roe_history | Single-dataset line chart: ROE over time (fundamental ratio, single axis) |
| `historical_summary` | summary | KPI strip (per-share + ratio + averages + percentile) + summary table. **Metric-aware**: renders TTM Earnings for lpa/dpa, PL for vpa. |
| `historical_dashboard` (v1.2) | dashboard | **Dashboard adapter** — multi-tab dashboard (Overview + Ratios + Summary). Thin pass-through of the `historical.dashboard()` tab payload |

```python
# LPA + P/L dual-dataset chart
report(action="chart", title="PETR4 LPA + P/L",
       data=<lpa_history JSON>, config={"chart_type":"line","adapter":"historical_lpa_chart"})

# VPA + P/VPA dual-dataset chart
report(action="chart", title="PETR4 VPA + P/VPA",
       data=<vpa_history JSON>, config={"chart_type":"line","adapter":"historical_vpa_chart"})

# DPA + Div Yield dual-dataset chart
report(action="chart", title="PETR4 DPA + Div Yield",
       data=<dpa_history JSON>, config={"chart_type":"line","adapter":"historical_dpa_chart"})

# Summary table (works for all metrics — reads result["metric"])
report(action="table", title="PETR4 Summary",
       data=<summary JSON>, config={"adapter":"historical_summary"})
```

---

## 🔌 Engine API (for direct import)

**Engines live in calculations/** — see [calculations/API.md](../calculations/API.md#-engine-api-for-direct-import) for the full engine API (all 18 engines with function signatures). Engines are standalone — importable by any consumer skill (historical, valuation, financials, future backtest).

Quick reference (import path: `skills.cvm.calculations.engines.<name>`):

| Engine | Category | Functions |
|---|---|---|
| `price` | market | `price_at()`, `price_series()` |
| `dividends` | market | `dividends_at()`, `dividends_periods()` |
| `shares` | shares | `shares_at()`, `shares_periods()` |
| `earnings` | dre | `ttm_earnings_at()`, `ttm_earnings_periods()` |
| `revenue` | dre | `revenue_at()`, `revenue_periods()` |
| `gross_profit` | dre | `gross_profit_at()`, `gross_profit_periods()` |
| `ebit` | dre | `ebit_at()`, `ebit_periods()` |
| `tax` | dre | `tax_at()`, `tax_periods()` |
| `assets` | bpa | `assets_at()`, `assets_periods()` |
| `total_assets` | bpa | `total_assets_at()`, `total_assets_periods()` |
| `cash` | bpa | `cash_at()`, `cash_periods()` |
| `pl` | bpp | `pl_at()`, `pl_periods()` |
| `debt` | bpp | `debt_at()`, `debt_periods()` |
| `current_liabilities` | bpp | `current_liabilities_at()`, `current_liabilities_periods()` |
| `da` | dfc | `da_at()`, `da_periods()` |
| `capex` | dfc | `capex_at()`, `capex_periods()` |

---

## 📐 Metric API (for direct import)

**Metrics live in calculations/** — see [calculations/API.md](../calculations/API.md#-metric-api-for-direct-import) for the full metric API (all 21 metrics with function signatures). Each per-share+ratio metric (Type 1) produces BOTH a per-share value AND a price ratio. Some metrics also produce bonus ratios. Each fundamental ratio metric (Type 2) produces only a ratio.

Quick reference (import path: `skills.cvm.calculations.metrics.<name>`):

| Metric | Type | Functions |
|---|---|---|
| `lpa` | 1 | `lpa_at()`, `pe_at()`, `lpa_history()` |
| `vpa` | 1 | `vpa_at()`, `pvpa_at()`, `vpa_history()` |
| `dpa` | 1 | `dpa_at()`, `dy_at()`, `payout_at()`, `dpa_history()` |
| `rps` | 1 | `rps_at()`, `psr_at()`, `rps_history()` |
| `ev_ebitda` | 1 | `ebitda_ps_at()`, `ev_ebitda_at()`, `ev_ebitda_history()` |
| `roe` | 2 | `roe_at()`, `roe_history()` |
| `roa` | 2 | `roa_at()`, `roa_history()` |
| `roic` | 2 | `roic_at()`, `roic_history()` |
| `gross_margin` | 2 | `gross_margin_at()`, `gross_margin_history()` |
| `operating_margin` | 2 | `operating_margin_at()`, `operating_margin_history()` |
| `net_margin` | 2 | `net_margin_at()`, `net_margin_history()` |
| `ebitda_margin` | 2 | `ebitda_margin_at()`, `ebitda_margin_history()` |
| `debt_equity` | 2 | `debt_equity_at()`, `debt_equity_history()` |
| `net_debt_ebitda` | 2 | `net_debt_ebitda_at()`, `net_debt_ebitda_history()` |
| `asset_turnover` | 2 | `asset_turnover_at()`, `asset_turnover_history()` |
| `capex_revenue` | 2 | `capex_revenue_at()`, `capex_revenue_history()` |
| `current_ratio` | 2 | `current_ratio_at()`, `current_ratio_history()` |

---

## 📐 Registry API

**The registry lives in calculations/** — see [calculations/API.md](../calculations/API.md#-registry-api) for the full registry API. Historical imports the registry helpers from `skills.cvm.calculations._registry`:

```python
from skills.cvm.calculations._registry import (
    ENGINES, METRICS,
    register_engine, register_metric, resolve_metric,
    list_engines, list_metrics, list_all_metric_names,
    list_engine_categories,
    EngineSpec, MetricSpec,
)
```

Historical uses `resolve_metric()` (canonical name + alias resolution) for `ratio_history()` + `summary()` dispatch. The MANIFEST in `historical/__init__.py` auto-generates `<metric>_history` modes by iterating `METRICS`.

---

*Last updated: 2026-08-06 (v1.20 — `skills/_base.py` extraction; modes + params + return shapes unchanged). See [ARCHITECTURE.md](ARCHITECTURE.md) for the updated source code reference, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules, [calculations/API.md](../calculations/API.md) for engine/metric/registry API.*
