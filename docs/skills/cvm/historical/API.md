<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 📝 API Reference

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

### `mode="ratio_history"` (generic)
Any metric over time. Accepts canonical names and aliases.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `lpa` | Metric name or alias (see table below) |
| `months` | `int` | `60` | Number of months |

**Metric names + aliases:**

| Canonical | Aliases | Per-share | Ratio |
|---|---|---|---|
| `lpa` | `pe`, `pl`, `p/l` | LPA (earnings/shares) | P/L (price/LPA) |
| `vpa` | `pvpa`, `p/vpa` | VPA (pl/shares) | P/VPA (price/VPA) |

**Error cases:**
- Missing company → `{"status": "error", "error": "company is required"}`
- Unknown metric → `{"status": "error", "error": "Unknown metric '<name>'. Available: ['lpa', 'vpa']"}`

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

Chart adapters are auto-registered for each metric. The summary adapter is metric-aware.

| Adapter | Source mode | What it renders |
|---|---|---|
| `historical_lpa_chart` | lpa_history | Dual-dataset line chart: LPA (per-share) + P/L (ratio) |
| `historical_vpa_chart` | vpa_history | Dual-dataset line chart: VPA (per-share) + P/VPA (ratio) |
| `historical_summary` | summary | KPI strip (per-share + ratio + averages + percentile) + summary table. **Metric-aware**: renders TTM Earnings for lpa, PL for vpa. |

```python
# LPA + P/L dual-dataset chart
report(action="chart", title="PETR4 LPA + P/L",
       data=<lpa_history JSON>, config={"chart_type":"line","adapter":"historical_lpa_chart"})

# VPA + P/VPA dual-dataset chart
report(action="chart", title="PETR4 VPA + P/VPA",
       data=<vpa_history JSON>, config={"chart_type":"line","adapter":"historical_vpa_chart"})

# Summary table (works for both metrics — reads result["metric"])
report(action="table", title="PETR4 Summary",
       data=<summary JSON>, config={"adapter":"historical_summary"})
```

---

## 🔌 Engine API (for direct import)

Engines are standalone — importable by any skill (e.g., future backtest).

### `engines/price.py`
```python
price_at(ticker: str, date: str) -> float | None          # close on date (or nearest <= date)
price_series(ticker: str, date_from: str, date_to: str) -> list[dict]  # [{date, close}, ...]
```

### `engines/earnings.py`
```python
ttm_earnings_at(company: str, date: str) -> float | None   # TTM earnings ending <= date (BRL)
ttm_earnings_periods(company: str) -> list[dict]           # [{date, ttm}, ...] sorted oldest-first
```

### `engines/shares.py`
```python
shares_at(company: str, date: str) -> int | None           # shares outstanding <= date
shares_periods(company: str) -> list[dict]                 # [{date, shares}, ...]
```

### `engines/pl.py`
```python
pl_at(company: str, date: str) -> float | None             # PL snapshot <= date (BRL)
pl_periods(company: str) -> list[dict]                     # [{date, pl}, ...]
```

---

## 📐 Metric API (for direct import)

Each metric produces BOTH a per-share value AND a price ratio.

### `metrics/lpa.py`
```python
lpa_at(company: str, date: str) -> float | None            # LPA = earnings / shares (per-share)
pe_at(company: str, date: str) -> float | None             # P/L = price / LPA (ratio)
lpa_history(company: str, date_from: str, date_to: str) -> list[dict]  # [{date, price, ttm_earnings, shares, lpa, pe}, ...]
```

### `metrics/vpa.py`
```python
vpa_at(company: str, date: str) -> float | None            # VPA = pl / shares (per-share)
pvpa_at(company: str, date: str) -> float | None           # P/VPA = price / VPA (ratio)
vpa_history(company: str, date_from: str, date_to: str) -> list[dict]  # [{date, price, pl, shares, vpa, pvpa}, ...]
```

---

## 📐 Registry API (for skill-internal use)

### `metrics/_registry.py`
```python
MetricSpec(name, per_share_label, per_share_key, per_share_fn,
           ratio_label, ratio_key, ratio_fn, history_fn, engines, aliases)

METRICS: dict[str, MetricSpec]              # all registered metrics
register_metric(spec: MetricSpec) -> MetricSpec  # called at import time by each metric
resolve_metric(name: str) -> MetricSpec      # canonical name or alias → spec
list_metrics() -> list[str]                  # canonical names only
list_all_names() -> list[str]                # canonical + aliases
```

---

*Last updated: 2026-07-26 (v1.2 — auto-discovery + registry). See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
