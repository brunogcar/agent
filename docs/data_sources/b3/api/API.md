<- Back to [API Overview](../API.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download B3 data via JSON API and store to SQLite.

| Param | Type | Default | Description |
|---|---|---|---|
| `table` | `str` | `"instruments"` | instruments, trades, after_hours, derivatives |
| `date_str` | `str` | today | YYYY-MM-DD |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="status"`
Show sync status for all B3 tables (no params).

### `mode="query"`
Query B3 data from local SQLite.

| Param | Type | Default | Description |
|---|---|---|---|
| `table` | `str` | `"instruments"` | Table name |
| `ticker` | `str` | `""` | Ticker symbol filter |
| `columns` | `list[str]` | all | Specific columns |
| `filters` | `dict` | `{}` | {column: value} filters |
| `limit` | `int` | `100` | Max rows |

### `mode="lookup_ticker"`
Look up a single ticker.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | Ticker symbol |

### `mode="search_company"`
Search instruments by company name.

| Param | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | (required) | Company name fragment |
| `limit` | `int` | `20` | Max results |

## Tool Invocation

```python
data_source(domain="b3", sub_domain="api", mode="sync")
data_source(domain="b3", sub_domain="api", mode="sync", params='{"table":"trades"}')
data_source(domain="b3", sub_domain="api", mode="query", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="api", mode="lookup_ticker", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="api", mode="search_company", params='{"name":"PETROBRAS"}')
```

---

*Last updated: 2026-07-23 (v1.0).*
