<- Back to [B3 Overview](../B3.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download dividends for a specific ticker.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | Full ticker (e.g., PETR4, VALE3) |
| `force` | `bool` | `false` | Re-download even if already synced |

### `mode="status"`
Show dividends DB stats (no params).

### `mode="dividends"`
Query cash dividends for a ticker.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | Ticker symbol |
| `limit` | `int` | `50` | Max results |

### `mode="stock_dividends"`
Query stock dividends (bonus shares).

### `mode="subscriptions"`
Query subscription rights.

## Tool Invocation

```python
data_source(domain="b3", sub_domain="dividends", mode="sync", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="dividends", mode="dividends", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="dividends", mode="status")
```

## Manual Sync

```powershell
python -c "from data_sources.b3.dividends.sync_engine import sync; print(sync(ticker='PETR4'))"
python -c "from data_sources.b3.dividends.sync_engine import sync; print(sync(ticker='VALE3'))"
```

---

*Last updated: 2026-07-23 (v1.0).*
