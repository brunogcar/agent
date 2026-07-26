<- Back to [BRAPI Overview](../BRAPI.md)

# 📝 API Reference

## Modes

### `mode="sync_tickers"`
Sync the full ticker list from brapi.dev (~1,796 tickers in 1 call). Replaces the 7,138-page InstrumentsConsolidated sync.

| Param | Type | Default | Description |
|---|---|---|---|
| `force` | `bool` | `false` | Re-fetch even if recently synced |

### `mode="sync_history"`
Sync historical OHLCV for a ticker from brapi.dev.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | B3 ticker (PETR4) |
| `range` | `str` | `1y` | Time range: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max |
| `interval` | `str` | `1d` | Bar interval: 1d, 5d, 1wk, 1mo, 3mo |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="quote"`
Get latest quote (price, market cap, P/E, volume). Tries local DB first, then live.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | B3 ticker |
| `force` | `bool` | `false` | Always fetch live from brapi.dev |

### `mode="history"`
Query historical OHLCV from local DB.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | B3 ticker |
| `days` | `int` | `30` | Number of days of history |

### `mode="tickers"`
List all synced tickers (no params).

### `mode="status"`
Show brapi.db stats (no params).

## Tool Invocation

```python
data_source(domain="b3", sub_domain="brapi", mode="sync_tickers")
data_source(domain="b3", sub_domain="brapi", mode="sync_history", params='{"ticker":"PETR4","range":"5y"}')
data_source(domain="b3", sub_domain="brapi", mode="quote", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="brapi", mode="history", params='{"ticker":"PETR4","days":90}')
data_source(domain="b3", sub_domain="brapi", mode="tickers")
data_source(domain="b3", sub_domain="brapi", mode="status")
```

---

*Last updated: 2026-07-25 (v1.0).*
