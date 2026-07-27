<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 📝 API Reference

The historical skill exposes one `<metric>_history` mode per registered metric (auto-generated from the calculations registry), plus two generic modes (`ratio_history`, `summary`). Engine, metric, and registry function signatures live in the calculations library — see [calculations/API.md](../calculations/API.md) for those.

## 🔧 Modes

### Auto-generated `<metric>_history` modes

The `<metric>_history` modes are auto-generated from the calculations metric registry. When a new metric is registered (in `skills/cvm/calculations/metrics/`), its `<metric>_history` mode appears here automatically. The 17 current modes are: `lpa_history`, `vpa_history`, `dpa_history`, `rps_history`, `ev_ebitda_history`, `roe_history`, `roa_history`, `roic_history`, `gross_margin_history`, `operating_margin_history`, `net_margin_history`, `ebitda_margin_history`, `debt_equity_history`, `net_debt_ebitda_history`, `asset_turnover_history`, `capex_revenue_history`, `current_ratio_history`.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `months` | `int` | `60` | Number of months of history (60 = 5 years) |

#### Example: `mode="lpa_history"` (per-share + ratio — Type 1)

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

#### Example: `mode="roe_history"` (fundamental ratio — Type 2, no per-share, no price)

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

**Note:** Type 1 series (lpa, vpa, dpa, rps, ev_ebitda) are daily (~1200 points over 5 years, driven by price dates). Type 2 series (roe, roa, roic, all margins, leverage, turnover, liquidity) have ~4-8 data points per year (quarterly earnings + balance snapshots) — no daily price driver. No `price` or `shares` in Type 2 series entries.

---

### `mode="ratio_history"` (generic, alias-aware)

Any metric over time. Accepts canonical names and aliases via `resolve_metric()`.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `lpa` | Metric name or alias (see table below) |
| `months` | `int` | `60` | Number of months |

**Metric names + aliases** (canonical name + PT/EN aliases — full table in [calculations/API.md](../calculations/API.md#metric-aliases-pt--en)):

| Canonical | Aliases (EN + PT) | Type |
|---|---|---|
| `lpa` | pe, pl, p/l, preco_lucro | Per-share+ratio |
| `vpa` | pvpa, p/vpa, preco_vpa, p_vpa | Per-share+ratio |
| `dpa` | dy, dividend_yield, yld, payout, rendimento, rendimento_dividendo, div_yield | Per-share+ratio (+payout) |
| `rps` | psr, p/sr, price_sales, preco_venda, p_venda | Per-share+ratio |
| `ev_ebitda` | ev_ebit, evebitda, eva_ebitda | Per-share+ratio (6 engines) |
| `roe` | return_on_equity, retorno_pl, retorno_patrimonio | Fundamental |
| `roa` | return_on_assets, retorno_ativos | Fundamental |
| `roic` | return_on_invested_capital, retorno_capital_investido | Fundamental (5 engines) |
| `gross_margin` | margem_bruta, gm, gross_margin_pct | Fundamental |
| `operating_margin` | margem_operacional, om, operating_margin_pct | Fundamental |
| `net_margin` | nm, margem_liquida, ml, net_margin_pct | Fundamental |
| `ebitda_margin` | em, margem_ebitda, ebitda_margin_pct | Fundamental |
| `debt_equity` | de, divida_pl, divida_patrimonio | Fundamental |
| `net_debt_ebitda` | nde, dl_ebitda, divida_liquida_ebitda, net_debt_to_ebitda | Fundamental |
| `asset_turnover` | at, giro_ativos, asset_turnover_ratio | Fundamental |
| `capex_revenue` | capex_intensity, intensidade_capex | Fundamental |
| `current_ratio` | cr, current_liquidity, liquidez_corrente | Fundamental |

**Error cases:**
- Missing company → `{"status": "error", "error": "company is required"}`
- Unknown metric → `{"status": "error", "error": "Unknown metric '<name>'. Available: [...]"}`

Return shape is identical to the matching `<metric>_history` mode.

---

### `mode="summary"` (generic, metric-aware, with percentile)

Current ratio vs 1Y/3Y/5Y average + min/max/percentile. Metric-aware: includes per-share value AND ratio in the result for Type 1 metrics; only the ratio for Type 2 fundamental metrics.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `lpa` | Metric name or alias |
| `months` | `int` | `60` | History window for percentile (always uses `max(months, 60)`) |

Returns (Type 1 metric — lpa):
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

Returns (Type 2 metric — roe): same shape, but `current` has no `price`/`shares`, only the ratio + engine components, and `per_share_label` is `null`.

**Interpretation thresholds (all metrics):**
| Percentile | Interpretation |
|---|---|
| ≤ 25 | cheap (below 25th percentile of history) |
| 25–75 | fair (between 25th-75th percentile of history) |
| ≥ 75 | expensive (above 75th percentile of history) |

**Error cases:**
- Missing company → `{"status": "error", "error": "company is required"}`
- Unknown metric → `{"status": "error", "error": "Unknown metric '<name>'. Available: [..."}`
- No price data → `{"status": "not_found", "error": "No price data for '<company>'"}`
- No valid ratio data (negative earnings/equity in window) → `{"status": "not_found", "error": "No valid <label> data for '<company>' (possibly negative earnings/equity)"}`

---

## 🛠️ Tool Invocation

```python
# LPA + P/L time series (auto-generated mode)
skill(domain="cvm", sub_domain="historical", mode="lpa_history", params='{"company":"PETR4","months":60}')

# VPA + P/VPA time series
skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')

# ROE fundamental ratio time series (Type 2 — ~4-8 points/year, not daily)
skill(domain="cvm", sub_domain="historical", mode="roe_history", params='{"company":"PETR4","months":60}')

# Summary (default metric = lpa)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')

# Summary for any metric (accepts aliases)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"vpa"}')
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"retorno_pl"}')

# Generic ratio history (accepts aliases: pe → lpa, pvpa → vpa, dy → dpa)
skill(domain="cvm", sub_domain="historical", mode="ratio_history", params='{"company":"PETR4","metric":"dy","months":120}')
```

---

## 📊 Report Adapters

Chart adapters are auto-registered for each metric from the calculations registry. The summary adapter is metric-aware.

| Adapter | Source mode | What it renders |
|---|---|---|
| `historical_lpa_chart` | lpa_history | Dual-dataset line chart: LPA (per-share) + P/L (ratio) |
| `historical_vpa_chart` | vpa_history | Dual-dataset line chart: VPA (per-share) + P/VPA (ratio) |
| `historical_dpa_chart` | dpa_history | Dual-dataset line chart: DPA (per-share) + Div Yield (ratio) |
| `historical_rps_chart` | rps_history | Dual-dataset line chart: RPS (per-share) + PSR (ratio) |
| `historical_ev_ebitda_chart` | ev_ebitda_history | Dual-dataset line chart: EBITDA/Ação (per-share) + EV/EBITDA (ratio) |
| `historical_roe_chart` | roe_history | Single-dataset line chart: ROE over time (fundamental ratio, single axis) |
| `historical_<metric>_chart` | `<metric>_history` | One per metric. Dual-dataset for Type 1, single-dataset for Type 2. Auto-registered. |
| `historical_summary` | summary | KPI strip (per-share + ratio + averages + percentile) + summary table. **Metric-aware**: shows per-share KPI/row for Type 1, skips it for Type 2. |

```python
# LPA + P/L dual-dataset chart
report(action="chart", title="PETR4 LPA + P/L",
       data=<lpa_history JSON>, config={"chart_type":"line","adapter":"historical_lpa_chart"})

# ROE single-dataset chart (fundamental ratio)
report(action="chart", title="PETR4 ROE",
       data=<roe_history JSON>, config={"chart_type":"line","adapter":"historical_roe_chart"})

# Summary table (works for all metrics — reads result["metric"])
report(action="table", title="PETR4 Summary",
       data=<summary JSON>, config={"adapter":"historical_summary"})
```

---

## 🔌 Engine + Metric + Registry API

Engines, metrics, and the central registry live in the **calculations library** at `skills/cvm/calculations/`. They are importable directly by any CVM skill (historical, future valuation/financials/backtest).

**See [calculations/API.md](../calculations/API.md) for:**
- All 16 engine function signatures (`*_at()` + `*_periods()` per engine, organized by category: market, shares, dre, bpa, bpp, dfc)
- All 17 metric function signatures (5 per-share+ratio + 12 fundamental ratio)
- Registry API (`EngineSpec`, `MetricSpec`, `register_engine`, `register_metric`, `resolve_metric`, `list_engines(category=...)`, `list_metrics`, `list_all_metric_names`, `list_engine_categories`)
- Full metric aliases table (PT + EN)
- Error handling (None returns, negative denominators, DPA 0.0 vs None, unknown metric dispatch)

**Direct import examples** (for backtests / custom analysis — bypassing the skill() dispatcher):

```python
# Engines — fetch ONE raw quantity at a historical date
from skills.cvm.calculations.engines.price import price_at, price_series
from skills.cvm.calculations.engines.earnings import ttm_earnings_at
from skills.cvm.calculations.engines.pl import pl_at
from skills.cvm.calculations.engines.da import da_at

# Metrics — compose engines into a ratio
from skills.cvm.calculations.metrics.lpa import lpa_at, pe_at, lpa_history
from skills.cvm.calculations.metrics.roe import roe_at
from skills.cvm.calculations.metrics.ev_ebitda import ev_ebitda_at

# Registry — discover engines/metrics, resolve aliases
from skills.cvm.calculations._registry import (
    list_engines, list_metrics, resolve_metric, ENGINES, METRICS,
)
```

---

*Last updated: 2026-07-26 (v2.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for mode dispatch + percentile analysis, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules. Engine/metric/registry API: [calculations/API.md](../calculations/API.md).*
