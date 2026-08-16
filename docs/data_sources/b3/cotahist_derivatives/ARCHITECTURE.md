<- Back to [COTAHIST_DERIVATIVES Overview](../COTAHIST_DERIVATIVES.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|---|---|
| `data_sources/b3/cotahist_derivatives/__init__.py` | MANIFEST (sub-domain hub — declares BDI codes + modes). No `route()` (no `@tool` entry — accessed via direct Python imports). |
| `data_sources/b3/cotahist_derivatives/catalog.py` | Schema constants: `DERIVATIVES_BDI_FILTER`, `DERIVATIVES_MARKET_TYPES`, `BDI_LABELS`, `_CALL_MONTHS`, `_PUT_MONTHS`, `parse_option_ticker()`, `DERIVATIVES_SCHEMA_SQL`, `db_path()`, `connect()`, `ensure_schema()`. Reuses `data_sources/b3/cotahist/catalog.db_path()` (shared DB). |
| `data_sources/b3/cotahist_derivatives/query_engine.py` | 4 query functions: `options_chain`, `available_maturities`, `put_call_ratio`, `volume_by_strike`. All accept `underlying` (PETR or PETR4) + optional `maturity`. |
| `data_sources/b3/cotahist_derivatives/status_reporter.py` | `stats()` — total rows, distinct underlyings, distinct maturities, date range, breakdown by `option_type`. |

> **No `sync_engine.py`** — derivatives are populated by the STANDARD
> COTAHIST sync (`data_sources/b3/cotahist/sync_engine.py`). The sync
> engine writes to BOTH tables in one ZIP parse pass: equities rows (BDI
> {02, 12, 14, 96}) → `cotahist` table; derivatives rows (BDI {78, 82, 83,
> 84, 26}) → `cotahist_derivatives` table. The ticker is parsed via
> `parse_option_ticker()` during sync to populate the derived columns.

## Data Flow

```
Download: https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP
  ↓
Unzip → COTAHIST_A{year}.TXT (~765MB, latin-1 encoding)
  ↓
Stream parse: line-by-line (245 bytes/record, 26 columns)
  ↓
Per-row BDI dispatch (in data_sources/b3/cotahist/sync_engine.py):
  ├─ BDI in {02, 12, 14, 96}  → INSERT into cotahist (equities)
  └─ BDI in {78, 82, 83, 84, 26}  → parse_option_ticker(symbol)
                                     → {underlying, option_type, expiration_month, strike_parsed}
                                     → INSERT into cotahist_derivatives
  ↓
Batch INSERT (50,000 rows per transaction, both tables)
  ↓
Record sync_state (year, rows_added, duration_s)  ← cotahist_sync_state only
```

## DB Schema (`cotahist_derivatives` table)

Same base columns as the equities `cotahist` table + 4 derived columns
parsed from the option ticker during sync:

| Column | Type | Source | Description |
|---|---|---|---|
| `id` | INTEGER PK | auto | Row id |
| `refdate` | TEXT | COTAHIST | Trade date (YYYY-MM-DD) |
| `bdi_code` | INTEGER | COTAHIST | BDI market segment (78/82/83/84/26) |
| `symbol` | TEXT | COTAHIST | Option ticker (e.g. `PETRH36`) |
| `market_type` | INTEGER | COTAHIST | 60=call, 70=put, 13=term, 17/20=forward |
| `corp_name` | TEXT | COTAHIST | Issuer name |
| `spec_code` | TEXT | COTAHIST | ISIN-like spec |
| `open` / `high` / `low` / `average` / `close` | REAL | COTAHIST | OHLC + average (÷100) |
| `best_bid` / `best_ask` | REAL | COTAHIST | Best bid/ask (÷100) |
| `trade_count` | INTEGER | COTAHIST | Number of trades |
| `contracts` | INTEGER | COTAHIST | Contracts traded |
| `volume` | REAL | COTAHIST | Financial volume (BRL) |
| `strike` | REAL | COTAHIST | Strike price (raw, ÷100) |
| `strike_adj` | TEXT | COTAHIST | Strike adjustment string |
| `maturity` | TEXT | COTAHIST | Expiration date (YYYY-MM-DD) |
| `lot_size` | INTEGER | COTAHIST | Contract multiplier |
| `strike_pts` | REAL | COTAHIST | Strike in points (index options) |
| `isin` | TEXT | COTAHIST | ISIN code |
| `dist_id` | INTEGER | COTAHIST | Distribution id |
| **`underlying`** | TEXT | **derived** | 4-letter code parsed from ticker (`"PETR"`) |
| **`option_type`** | TEXT | **derived** | `"CALL"` / `"PUT"` / `"TERM"` |
| **`expiration_month`** | INTEGER | **derived** | 1-12 (parsed from month code) |
| **`strike_parsed`** | REAL | **derived** | Strike as float, with half-point rule (`215` → 21.5) |
| `_ingested_at` | TEXT | auto | Sync timestamp |

**Indexes (5):**
- `idx_deriv_symbol(symbol)`
- `idx_deriv_refdate(refdate)`
- `idx_deriv_underlying(underlying)`
- `idx_deriv_maturity(maturity)`
- `idx_deriv_underlying_maturity(underlying, maturity)` ← composite, hot path

**`cotahist_derivatives_sync_state`** table tracks per-year sync metadata
(year PK, synced_at, rows_added, duration_s).

## BDI Codes

| Code | Label | Notes |
|------|-------|-------|
| 78 | CALL | Stock call options |
| 82 | PUT | Stock put options |
| 83 | CALL (index) | Index call options (e.g. IBovespo mini-index) |
| 84 | PUT (index) | Index put options |
| 26 | TERM | Forward contracts (OTC-style, no ticker convention) |

**Market types** (`DERIVATIVES_MARKET_TYPES`): `{13, 17, 20, 60, 70}` —
13=term, 17=forward with gain retention, 20=forward with continuous
movement, 60=call, 70=put.

## Option Ticker Parser (`parse_option_ticker`)

Parses a B3 option ticker into `{underlying, option_type,
expiration_month, expiration_month_name, strike_parsed}`.

**Format:** `UNDERLYING + MONTH_CODE + STRIKE`
- UNDERLYING: 4-5 letters (before the month code)
- MONTH_CODE: 1 letter — `A-L` for calls (Jan-Dec), `M-X` for puts (Jan-Dec)
- STRIKE: 2-4 digits — trailing `5` = half-point (e.g. `215` → 21,50)

**Examples:**
| Ticker | Underlying | Type | Month | Strike |
|--------|-----------|------|-------|--------|
| `PETRH36` | PETR | CALL | 8 (Aug) | 36.00 |
| `PETRT36` | PETR | PUT | 8 (Aug) | 36.00 |
| `PETRA215` | PETR | CALL | 1 (Jan) | 21.50 |
| `PETRA3650` | PETR | CALL | 1 (Jan) | 365.00 |

Returns `None` for non-option tickers (e.g. equity `"PETR4"` has a digit
at position 4, not a letter — fails the month-code lookup).

## Design Decisions

- **Shared DB (cotahist.db)** — derivatives live in the same SQLite file
  as equities. Avoids a separate connection + separate sync command + a
  second `cotahist_derivatives.db` file. The `db_path()` helper delegates
  to `data_sources/b3/cotahist/catalog.db_path()`.
- **No separate sync_engine** — the standard COTAHIST sync writes to both
  tables in one ZIP parse pass (the BDI dispatch happens per row). This
  means `REQUIRED_SOURCES = ["cotahist"]` is sufficient for the options
  skill (no `"cotahist_derivatives"` entry needed in
  `skills/_base._trigger_sync.sync_map`).
- **Derived columns at sync time** — `underlying`, `option_type`,
  `expiration_month`, `strike_parsed` are parsed from the ticker ONCE
  during sync and stored as columns (with indexes). This makes per-
  underlying + per-strike queries fast (no runtime ticker parsing per
  row). The half-point rule (`215` → 21.50) is baked in.
- **BDI dispatch in the sync engine, not in the catalog** — the sync engine
  reads a row, checks `bdi_code` against the equities filter {02, 12, 14,
  96}, else checks against the derivatives filter {78, 82, 83, 84, 26}.
  Rows that match neither are skipped (bonds, warrants, etc.).
- **Nearest maturity auto-selection** — `options_chain` / `volume_by_strike`
  pick the nearest future expiration date (or the most recent past one if
  no future maturities exist) when `maturity` is empty. This gives callers
  a sensible default without a UI selector.

---

*Last updated: 2026-08-18 (v1.0).*
