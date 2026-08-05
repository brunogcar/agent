<- Back to [INDEX Overview](../INDEX.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/b3/index/__init__.py` | MANIFEST + route — sub-domain hub, 8 modes |
| `data_sources/b3/index/catalog.py` | Schema constants: API URLs, CATALOG (26 indices), ACTIVE_INDICES (5), SQL schema, DB path/connect helpers |
| `data_sources/b3/index/sync_engine.py` | `sync_index(index)` (single) + `sync_all()` (5 active). Downloads composition + historical values JSON per index. DELETE + INSERT per index (idempotent). |
| `data_sources/b3/index/query_engine.py` | Query: `index()` composition, `search()` catalog, `summary()` DB stats, `history()` OHLCV, `ticker()` reverse-lookup. |
| `data_sources/b3/index/status_reporter.py` | DB stats (indices synced, last sync, total constituents, total history rows). |

## Database Schema

Three tables in `memory_db/b3/index.db`:

### `indices` — index catalog + sync state

| Column | Type | Description |
|---|---|---|
| symbol | text PK | Index symbol (IBOV, SMLL) |
| name | text | Full name (Índice Bovespa) |
| description | text | Long-form description |
| index_type | text | Type: broad / sector / strategy / size |
| active | int | 1 if in ACTIVE_INDICES, 0 if catalog-only |
| last_synced_at | text | ISO timestamp of last successful sync |

### `constituents` — current index composition

| Column | Type | Description |
|---|---|---|
| index_symbol | text | FK → indices.symbol |
| ticker | text | Constituent ticker (PETR4) |
| isin | text | ISIN code (optional) |
| weight | real | Weight in index (0.0–1.0) |
| position | int | Position rank (1 = highest weight) |
| refdate | text | Composition reference date YYYY-MM-DD |

Primary key: (index_symbol, ticker, refdate).

### `history` — daily OHLCV per index

| Column | Type | Description |
|---|---|---|
| index_symbol | text | FK → indices.symbol |
| refdate | text | Trading date YYYY-MM-DD |
| open | real | Opening value |
| high | real | Intraday high |
| low | real | Intraday low |
| close | real | Closing value |
| variation_pct | real | Daily variation (%) |
| volume | real | Traded volume (BRL) |

Primary key: (index_symbol, refdate).

A `sync_state` table also tracks per-index sync progress (rows_added, duration_s, errors).

## API Flow

```
sync_index("IBOV")
  ↓
GET GetPortfolioDay/{base64({"symbol":"IBOV","language":"pt-br"})}
  → JSON: {composition: [{ticker, weight, position, isin}], refdate}
  ↓
GET GetStockIndex/{base64({"symbol":"IBOV","language":"pt-br"})}
  → JSON: {history: [{refdate, open, high, low, close, variation_pct, volume}]}
  ↓
DELETE FROM indices      WHERE symbol='IBOV'
DELETE FROM constituents WHERE index_symbol='IBOV'
DELETE FROM history      WHERE index_symbol='IBOV'
  ↓
INSERT indices row (catalog metadata + last_synced_at)
INSERT constituents rows
INSERT history rows
  ↓
Record sync_state (index, rows_added, duration_s)
```

## Design Decisions

- **5 active + 26 catalogued**: B3 publishes 26 indices but only 5 are commonly used (IBOV, SMLL, BDRX, IFIX, IDIV). `sync_all()` syncs only the 5; `sync_index(index=...)` works for any of the 26.
- **DELETE + INSERT per index**: Idempotent re-syncs. No partial state if the API returns a different constituent set between syncs (e.g., quarterly rebalance).
- **Composition + history in one DB**: Indices are small (IBOV has ~80 constituents). One DB keeps joins cheap (e.g., ticker → indices reverse-lookup).
- **`ticker` reverse-lookup**: Common LLM query is "which indices does PETR4 belong to?". A `WHERE ticker=?` on `constituents` answers in O(log n).
- **Sync guard integration**: Skills using index data declare `required_sources=["index"]` in `__init__.py`. The `route()` wrapper calls `ensure_fresh()` before dispatch — force-syncs `index.db` if older than 24h (via `sync_all()`).
- **Weights normalized to 0.0–1.0**: B3 returns "5.23" meaning 5.23%. We divide by 100 at ingest so downstream ratios compose naturally.
- **No historical constituent changes tracked**: Only the current composition is stored (snapshot per sync). Historical constituent turnover (additions/removals at quarterly rebalances) is deferred — would need a `constituents_history` table.

---

*Last updated: 2026-08-05 (v1.0).*
