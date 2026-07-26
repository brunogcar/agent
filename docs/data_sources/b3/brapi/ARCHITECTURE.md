<- Back to [BRAPI Overview](../BRAPI.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/b3/brapi/__init__.py` | MANIFEST + route — sub-domain hub, 6 modes |
| `data_sources/b3/brapi/catalog.py` | Schema constants: API base URL, FREE_TICKERS, VALID_RANGES/INTERVALS, SQL schema (tickers + quotes + sync_state), DB path/connect helpers |
| `data_sources/b3/brapi/fetcher.py` | HTTP fetcher: `fetch_quote(ticker)` → JSON, `fetch_history(ticker, range, interval)` → OHLCV, `fetch_tickers()` → ticker list. Rate limiting (0.5s) + in-memory cache (1h TTL). |
| `data_sources/b3/brapi/sync_engine.py` | `sync_tickers()` — download 1,796 tickers in 1 call. `sync_history(ticker, range, interval)` — download OHLCV → store to SQLite. |
| `data_sources/b3/brapi/query_engine.py` | Query: `quote(ticker, force)` — latest price (local DB first, live fallback). `history(ticker, days)` — OHLCV from local DB. `tickers()` — list all synced tickers. |
| `data_sources/b3/brapi/status_reporter.py` | Status: brapi.db stats (tickers, OHLCV rows, symbols_with_history, last_sync). |

## API Flow

```
GET https://brapi.dev/api/quote/{ticker}
  ↓
JSON: {regularMarketPrice, marketCap, priceEarnings, ...}
  ↓
Cache in brapi.db quotes table (or return directly if force=True)

GET https://brapi.dev/api/available
  ↓
JSON: {stocks: [{stock: "PETR4", ...}, ...]}
  ↓
INSERT INTO tickers (symbol, synced_at) VALUES (...)

GET https://brapi.dev/api/quote/{ticker}?range=1y&interval=1d
  ↓
JSON: {results: [{date, open, high, low, close, adjustedClose, volume}, ...]}
  ↓
Epoch → YYYY-MM-DD conversion
INSERT INTO quotes (symbol, date, open, high, low, close, adjusted_close, volume)
```

## Design Decisions

- **1 call replaces 7,138 pages**: The B3 InstrumentsConsolidated API requires paginating 7,138 pages (~20 min). brapi.dev's `/available` endpoint returns all 1,796 tickers in 1 call (<1s).
- **Free tier coverage**: PETR4, VALE3, ITUB4, MGLU3 work without a token. Full coverage requires a free signup at brapi.dev.
- **Local-first quote**: `quote()` tries the local DB first (instant). Only fetches live from brapi.dev if not cached or `force=True`.
- **Rate limiting + caching**: The fetcher has a 0.5s rate limit and 1-hour in-memory cache to avoid hitting brapi.dev too frequently.
- **Epoch conversion**: brapi.dev returns dates as epoch milliseconds. Converted to YYYY-MM-DD for SQLite sorting.

---

*Last updated: 2026-07-25 (v1.0).*
