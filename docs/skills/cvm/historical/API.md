<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 📝 API Reference

## 🔧 Modes

### `mode="pe_history"` (default)
Daily P/L time series for the last N months.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `months` | `int` | `60` | Number of months of history (60 = 5 years) |

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "pe",
  "date_from": "2019-07-26",
  "date_to": "2024-07-26",
  "total_days": 1200,
  "pe_days": 1100,
  "series": [
    {"date": "2019-07-26", "price": 28.5, "ttm_earnings": 100e9, "shares": 13e9, "pe": 3.7},
    ...
  ],
  "data_freshness": {...}
}
```

---

### `mode="vpa_history"`
Daily P/VPA time series for the last N months.

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
  "date_from": "2019-07-26",
  "date_to": "2024-07-26",
  "total_days": 1200,
  "vpa_days": 1100,
  "series": [
    {"date": "2019-07-26", "price": 28.5, "pl": 290e9, "shares": 13e9, "vpa": 1.27},
    ...
  ],
  "data_freshness": {...}
}
```

---

### `mode="ratio_history"`
Any metric over time. Dispatches to `pe_history` or `vpa_history` based on `metric`.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `pe` | Metric: `pe` or `vpa` |
| `months` | `int` | `60` | Number of months |

**Error cases:**
- Missing company → `{"status": "error", "error": "company is required"}`
- Unknown metric → `{"status": "error", "error": "Unknown metric '<name>'. Available: pe, vpa"}`

---

### `mode="summary"`
Current ratio vs 1Y/3Y/5Y average + min/max/percentile. Metric-aware.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `pe` | Metric: `pe` or `vpa` |
| `months` | `int` | `60` | History window for percentile (always uses max(months, 60) for percentile) |

Returns (metric=pe):
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "pe",
  "current": {
    "date": "2024-07-26",
    "pe": 5.34,
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
  "current": {
    "date": "2024-07-26",
    "vpa": 1.45,
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

**Interpretation thresholds (both metrics):**
| Percentile | Interpretation |
|---|---|
| ≤ 25 | cheap (below 25th percentile of history) |
| 25–75 | fair (between 25th-75th percentile of history) |
| ≥ 75 | expensive (above 75th percentile of history) |

**Error cases:**
- Missing company → `{"status": "error", "error": "company is required"}`
- No price data → `{"status": "not_found", "error": "No price data for '<company>'"}`
- No valid ratio data (negative earnings/equity) → `{"status": "not_found", "error": "No valid <label> data for '<company>' (possibly negative earnings/equity)"}`

---

## 🛠️ Tool Invocation

```python
# P/L time series
skill(domain="cvm", sub_domain="historical", mode="pe_history", params='{"company":"PETR4","months":60}')

# P/VPA time series
skill(domain="cvm", sub_domain="historical", mode="vpa_history", params='{"company":"PETR4","months":60}')

# Summary (P/L)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')

# Summary (P/VPA)
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4","metric":"vpa"}')

# Generic ratio history
skill(domain="cvm", sub_domain="historical", mode="ratio_history", params='{"company":"PETR4","metric":"vpa","months":120}')
```

---

## 📊 Report Adapters

| Adapter | Source mode | What it renders |
|---|---|---|
| `historical_pe_chart` | pe_history | Line chart (P/L over time, None = gaps) |
| `historical_vpa_chart` | vpa_history | Line chart (P/VPA over time, None = gaps) |
| `historical_summary` | summary | KPI strip (current, 1Y/3Y/5Y avg, percentile) + summary table. **Metric-aware**: renders P/L + TTM Earnings for pe, P/VPA + PL for vpa. |

```python
# P/L chart
report(action="chart", title="PETR4 P/L",
       data=<pe_history JSON>, config={"chart_type":"line","adapter":"historical_pe_chart"})

# P/VPA chart
report(action="chart", title="PETR4 P/VPA",
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

### `metrics/pe.py`
```python
pe_at(company: str, date: str) -> float | None             # P/L = price / (TTM / shares)
pe_history(company: str, date_from: str, date_to: str) -> list[dict]  # [{date, price, ttm_earnings, shares, pe}, ...]
```

### `metrics/vpa.py`
```python
vpa_at(company: str, date: str) -> float | None            # P/VPA = price / (PL / shares)
vpa_history(company: str, date_from: str, date_to: str) -> list[dict]  # [{date, price, pl, shares, vpa}, ...]
```

---

*Last updated: 2026-07-26 (v1.1 — added PL engine + VPA metric). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
