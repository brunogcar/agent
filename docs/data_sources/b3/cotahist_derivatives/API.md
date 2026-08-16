<- Back to [COTAHIST_DERIVATIVES Overview](../COTAHIST_DERIVATIVES.md)

# 📝 API Reference

All functions are direct Python imports — the `cotahist_derivatives`
sub-domain has NO `@tool` entry point (accessed by skills via direct
import, not through the `data_source()` dispatcher).

```python
from data_sources.b3.cotahist_derivatives.query_engine import (
    options_chain, available_maturities, put_call_ratio, volume_by_strike)
from data_sources.b3.cotahist_derivatives.status_reporter import stats
```

**Common conventions (apply to all query functions):**
- `underlying` accepts both the 4-letter code (`"PETR"`) and the full ticker
  (`"PETR4"`); trailing digits are stripped automatically. The `underlying`
  field in every response is the normalized 4-letter code.
- Every response includes a `status` field: `ok` | `error` (caller error:
  missing/invalid `underlying`) | `not_synced` (`cotahist.db` doesn't exist)
  | `not_found` (no data for this underlying / maturity).

---

## `options_chain(underlying, maturity="", limit=200)`

Get the options chain for an underlying + optional maturity. If `maturity`
is empty, picks the nearest future expiration date (or the most recent past
one if no future maturities exist).

| Param | Type | Default | Description |
|---|---|---|---|
| `underlying` | `str` | `""` | 4-letter code (`"PETR"`) or full ticker (`"PETR4"`). Required. |
| `maturity` | `str` | `""` | YYYY-MM-DD expiration date. Empty = nearest maturity. |
| `limit` | `int` | `200` | Max results. |

**Returns:** `{status, underlying, maturity, refdate, count, options: [...]}`.
Each option row has: `symbol, bdi_code, option_type, strike, strike_parsed,
maturity, close, volume, best_bid, best_ask, open, high, low, average,
trade_count, contracts, refdate`. Rows are ordered by `option_type` then
`strike_parsed` (calls first sorted by strike ascending, then puts sorted
by strike ascending).

```json
{"status": "ok", "underlying": "PETR", "maturity": "2026-08-17",
 "refdate": "2026-08-15", "count": 42,
 "options": [{"symbol": "PETRH36", "bdi_code": 78, "option_type": "CALL",
   "strike": 36.0, "strike_parsed": 36.0, "maturity": "2026-08-17",
   "close": 1.25, "volume": 12345000, "best_bid": 1.24, "best_ask": 1.26, ...}, ...]}
```

---

## `available_maturities(underlying)`

Get all distinct expiration dates for an underlying, with the row count per
maturity. Useful for building a maturity-selector UI.

| Param | Type | Default | Description |
|---|---|---|---|
| `underlying` | `str` | `""` | 4-letter code or full ticker. Required. |

**Returns:** `{status, underlying, maturities: [{maturity, count}, ...]}`.
Ascending by maturity. Useful for building a maturity-selector UI.

```json
{"status": "ok", "underlying": "PETR",
 "maturities": [{"maturity": "2026-08-17", "count": 42},
   {"maturity": "2026-09-21", "count": 38}, {"maturity": "2026-10-19", "count": 35}]}
```

---

## `put_call_ratio(underlying, days=90)`

Compute the daily put/call ratio (volume-based) for an underlying over the
last N trading days. `ratio = total put volume / total call volume` per
day. `ratio > 1` = bearish sentiment; `< 1` = bullish.

| Param | Type | Default | Description |
|---|---|---|---|
| `underlying` | `str` | `""` | 4-letter code or full ticker. Required. |
| `days` | `int` | `90` | Number of most-recent trading days. |

**Returns:** `{status, underlying, count, observations: [...]}`. Each
observation has `ref_date, call_volume, put_volume, ratio`. Observations
are ascending by date. `ratio = put_vol / call_vol`; `None` when
`call_volume == 0`. The SQL aggregation is
`SUM(CASE WHEN option_type='CALL' THEN volume ELSE 0 END)` grouped by
`refdate` — done in SQLite, not in Python.

```json
{"status": "ok", "underlying": "PETR", "count": 90,
 "observations": [
   {"ref_date": "2026-05-01", "call_volume": 1234567, "put_volume": 987654, "ratio": 0.8005},
   {"ref_date": "2026-05-02", "call_volume": 987654, "put_volume": 1111111, "ratio": 1.1250}, ...]}
```

---

## `volume_by_strike(underlying, maturity="")`

Get total volume + contract count per strike for an underlying + maturity,
for the latest trading day. Nearest maturity auto-selected if empty.

| Param | Type | Default | Description |
|---|---|---|---|
| `underlying` | `str` | `""` | 4-letter code or full ticker. Required. |
| `maturity` | `str` | `""` | YYYY-MM-DD. Empty = nearest maturity. |

**Returns:** `{status, underlying, maturity, refdate, count, strikes: [...]}`.
Each strike has `strike, call_volume, put_volume, call_count, put_count`.
Ascending by strike. Aggregates ALL option contracts at each strike for the
latest trading day (multiple strikes can exist for the same `strike_parsed`
across different expirations on the same maturity date — though rare).

```json
{"status": "ok", "underlying": "PETR", "maturity": "2026-08-17",
 "refdate": "2026-08-15", "count": 12,
 "strikes": [{"strike": 30.0, "call_volume": 123456, "put_volume": 45678,
   "call_count": 3, "put_count": 1}, ...]}
```

---

## `stats()`

DB summary for the `cotahist_derivatives` table.

```python
from data_sources.b3.cotahist_derivatives.status_reporter import stats
```

**Returns:** `{status, total_rows, underlyings, maturities, date_range, by_type}`.
`by_type` is grouped by the derived `option_type` column (`CALL`, `PUT`,
`TERM`, or `UNKNOWN` for rows where the ticker parse failed).

```json
{"status": "ok", "total_rows": 1234567, "underlyings": 120, "maturities": 450,
 "date_range": {"from": "2010-01-04", "to": "2026-08-15"},
 "by_type": {"CALL": 800000, "PUT": 400000, "TERM": 34567}}
```

---

*Last updated: 2026-08-18 (v1.0).*
