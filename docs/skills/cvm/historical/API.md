<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 📝 API Reference

## Modes

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

### `mode="ratio_history"`
Any metric over time. Currently only `pe` is implemented.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `pe` | Metric: pe, pvpa, ev_ebitda |
| `months` | `int` | `60` | Number of months |

### `mode="summary"`
Current ratio vs 1Y/3Y/5Y average + min/max/percentile.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | B3 ticker |
| `metric` | `str` | `pe` | Metric name |
| `months` | `int` | `60` | History window for percentile |

Returns:
```json
{
  "status": "ok",
  "company": "PETR4",
  "metric": "pe",
  "current": {"date": "2024-07-26", "pe": 5.34, "price": 38.5, "ttm_earnings": 134e9, "shares": 13e9},
  "averages": {"1y": 6.2, "3y": 7.5, "5y": 8.1},
  "range": {"min": 3.1, "max": 12.5},
  "percentile": 25.0,
  "interpretation": "cheap (below 25th percentile of history)",
  "data_points": 1100,
  "data_freshness": {...}
}
```

## Tool Invocation

```python
skill(domain="cvm", sub_domain="historical", mode="pe_history", params='{"company":"PETR4","months":60}')
skill(domain="cvm", sub_domain="historical", mode="summary", params='{"company":"PETR4"}')
```

## Report Adapters

| Adapter | Source mode | What it renders |
|---|---|---|
| `historical_pe_chart` | pe_history | Multi-series line chart (P/L over time) |
| `historical_summary` | summary | KPI strip (current, 1Y/3Y/5Y avg, percentile) + summary table |

---

*Last updated: 2026-07-25 (v1.0).*
