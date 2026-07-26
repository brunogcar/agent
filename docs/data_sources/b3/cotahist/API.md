<- Back to [COTAHIST Overview](../COTAHIST.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download + parse COTAHIST for one or more years (2010-present). ~87MB ZIP per year.

| Param | Type | Default | Description |
|---|---|---|---|
| `year` | `int` | current year | Single year (e.g., 2025). Ignored if `years` given. |
| `years` | `list[int]` | — | Multiple years. Takes precedence over `year`. |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="query"`
Query historical OHLCV from local DB. Filter by ticker, date range, or year.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | `""` | Ticker symbol (PETR4). Empty = all. |
| `date_from` | `str` | `""` | Start date YYYY-MM-DD |
| `date_to` | `str` | `""` | End date YYYY-MM-DD |
| `year` | `int` | `0` | Filter by year. Takes precedence over date_from/date_to. |
| `limit` | `int` | `100` | Max rows |
| `market_type` | `int` | `10` | Market type filter (10=spot, 0=all) |

### `mode="status"`
Show cotahist.db stats (no params).

## Tool Invocation

```python
data_source(domain="b3", sub_domain="cotahist", mode="sync", params='{"year":2025}')
data_source(domain="b3", sub_domain="cotahist", mode="sync", params='{"years":[2023,2024,2025]}')
data_source(domain="b3", sub_domain="cotahist", mode="query", params='{"ticker":"PETR4","year":2025}')
data_source(domain="b3", sub_domain="cotahist", mode="query", params='{"ticker":"VALE3","date_from":"2025-01-01","date_to":"2025-06-30"}')
data_source(domain="b3", sub_domain="cotahist", mode="status")
```

---

*Last updated: 2026-07-25 (v1.0).*
