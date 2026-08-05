<- Back to [INDEX Overview](../INDEX.md)

# 📝 API Reference

## Modes

### `mode="sync_index"`
Download composition + history for one index.

| Param | Type | Default | Description |
|---|---|---|---|
| `index` | `str` | (required) | Index symbol (IBOV, SMLL, BDRX, IFIX, IDIV) |
| `force` | `bool` | `false` | Re-download even if already synced |
| `history_days` | `int` | `365` | Days of historical values to fetch |

### `mode="sync_all"`
Sync all 5 active indices (IBOV, SMLL, BDRX, IFIX, IDIV). No params.

### `mode="index"`
Query current composition for an index.

| Param | Type | Default | Description |
|---|---|---|---|
| `index` | `str` | (required) | Index symbol |
| `limit` | `int` | `100` | Max constituents returned |

### `mode="search"`
Search the index catalog (26 catalogued indices).

| Param | Type | Default | Description |
|---|---|---|---|
| `q` | `str` | `""` | Name/symbol fragment (e.g., "ibo", "small") |
| `active_only` | `bool` | `true` | Restrict to the 5 active indices |

### `mode="summary"`
Index DB summary: total indices synced, last sync date, total constituents, total history rows. No params.

### `mode="history"`
Historical OHLCV values for an index.

| Param | Type | Default | Description |
|---|---|---|---|
| `index` | `str` | (required) | Index symbol |
| `date_from` | `str` | `""` | Start date YYYY-MM-DD |
| `date_to` | `str` | `""` | End date YYYY-MM-DD |
| `limit` | `int` | `100` | Max rows |

### `mode="ticker"`
Given a ticker, list all indices it belongs to + its weight in each.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | Ticker symbol (PETR4) |

### `mode="status"`
DB stats (no params).

## Tool Invocation

```python
data_source(domain="b3", sub_domain="index", mode="sync_index", params='{"index":"IBOV"}')
data_source(domain="b3", sub_domain="index", mode="sync_all")
data_source(domain="b3", sub_domain="index", mode="index", params='{"index":"IBOV"}')
data_source(domain="b3", sub_domain="index", mode="search", params='{"q":"ibo","active_only":false}')
data_source(domain="b3", sub_domain="index", mode="summary")
data_source(domain="b3", sub_domain="index", mode="history", params='{"index":"IBOV","limit":30}')
data_source(domain="b3", sub_domain="index", mode="ticker", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="index", mode="status")
```

## Manual Sync

```powershell
python -c "from data_sources.b3.index.sync_engine import sync_index; print(sync_index(index='IBOV'))"
python -c "from data_sources.b3.index.sync_engine import sync_all; print(sync_all())"
```

---

*Last updated: 2026-08-05 (v1.0).*
