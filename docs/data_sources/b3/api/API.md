<- Back to [API Overview](../API.md)

# 📝 API Reference

## Modes

### `mode="sync"`
Download B3 data via CSV bulk download API and store to SQLite.

[v2.0] Replaced the paginated JSON API (2,283 requests, 4 columns, 22 min)
with a 2-step CSV bulk download (1 request, 15-52 columns, ~1-10s).

[v2.1] Added partial data skip: if B3 returns "Status do Arquivo: Parcial"
(intraday snapshot), the sync skips and keeps the previous Final data.
Added retry with backoff (3 attempts) on both HTTP calls.

| Param | Type | Default | Description |
|---|---|---|---|
| `table` | `str` | `"instruments"` | instruments (52 cols), trades (15), after_hours (15), derivatives (17) |
| `date_str` | `str` | today | YYYY-MM-DD (falls back up to 7 days if no data) |
| `force` | `bool` | `false` | Re-download even if already synced (does NOT override partial data skip) |

**Partial data behavior**: B3 marks intraday snapshots as "Parcial" and
end-of-day data as "Final". If the sync detects "Parcial", it skips the
DELETE+INSERT and returns `{status: "skipped_partial"}`, preserving the
previous Final sync. To force a partial sync (not recommended), delete
the sync_state row manually before syncing.

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

### `mode="open_positions"` (v2.0)
Open interest + position breakdown for all options on an underlying. Queries
`derivatives.db` (DerivativesOpenPosition CSV bulk download) and joins
`instruments.db` (InstrumentsConsolidated) on `TckrSymb` to enrich each
option with strike (`ExrcPric`), expiration (`XprtnDt`), option style
(`OptnStyle`), and company name (`CrpnNm`). Used by the options skill's
"Posições em Aberto" tab.

Filters:
- Only `SgmtNm` = `EQUITY CALL` or `EQUITY PUT` (skips `FORWARD`,
  `FINANCIAL`, etc.).
- Skips rows with `OpnIntrst=0` AND `TtlPos=0` (no positions).

Graceful degradation:
- If `derivatives.db` is missing → `{status: "not_synced"}`.
- If `instruments.db` is missing → returns derivatives data with `strike=None`,
  `days_to_expiration=None`, `instruments_ok=false`.

| Param | Type | Default | Description |
|---|---|---|---|
| `underlying` | `str` | (required) | 4-letter code (`PETR`) or full ticker (`PETR4`). Trailing digits stripped. |

Returns:
```python
{
  "status": "ok",
  "underlying": "PETR",
  "refdate": "2026-09-08",
  "instruments_ok": true,
  "count": 8,
  "summary": {
    "CALL": {"oi": 112000, "covered": 42000, "blocked": 21000,
             "uncovered": 49000, "total": 112000, "holders": 67000,
             "writers": 45000, "covered_pct": 37.5, "uncovered_pct": 43.75},
    "PUT":  {...}
  },
  "by_strike": [
    {"strike": 36.0, "call_oi": 12000, "put_oi": 8000, "call_count": 1, "put_count": 1},
    ...
  ],
  "detail": [
    {"ticker": "PETRG36", "type": "CALL", "strike": 36.0,
     "expiration": "2026-08-17", "days_to_expiration": 313,
     "oi": 12000, "var_oi": 500, "covered": 4000, "uncovered": 6000,
     "total": 12000, "holders": 7000, "writers": 5000, "forward": 38.20},
    ...
  ]
}
```

### `mode="lookup_option_positions"` (v2.0)
Lighter single-ticker lookup — fetches one row from `derivatives.db`. Used by
the Cadeia de Opções tab to enrich each chain row with OI / Coberta /
Descoberta columns without a full `open_positions()` call.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | Option ticker (e.g. `PETRA201`, `PETRG36`). Case-insensitive. |

Returns `{status: "ok", ticker, oi, var_oi, covered, blocked, uncovered,
total, holders, writers, forward}` or `{status: "not_found"}`.

### `mode="forward_positions"` (v2.1)
Get the EQUITY FORWARD open position for a stock ticker. Constructs the
forward ticker (`{TICKER}T` — e.g. `PETR4` → `PETR4T`) and queries
`derivatives.db` `WHERE SgmtNm = 'EQUITY FORWARD'`, then joins
`instruments.db` on `TckrSymb` for company name, ISIN, security category,
and specification. Used by the term skill as the stock-term fallback when
COTAHIST has no term data (which is always — B3 routes stock term to BTC).

Computes `forward_price_per_share = FwdPric / CurQty` (the average agreed
forward price per share — the closest thing to a "term price" for stocks).

Graceful degradation:
- If `derivatives.db` is missing → `{status: "not_synced"}`.
- If `instruments.db` is missing → returns derivatives data with
  `company=""`, `isin=""`, `security_category=""`, `specification=""`,
  `instruments_ok=false`.
- If the forward ticker isn't in `derivatives.db` → `{status: "not_found"}`.
- If `FwdPric` or `CurQty` is missing/zero → `forward_price_per_share=null`.

| Param | Type | Default | Description |
|---|---|---|---|
| `ticker` | `str` | (required) | Stock ticker (e.g. `PETR4`, `VALE3`). Trailing digits are NOT stripped (`PETR4T` ≠ `PETR3T`). If the ticker already ends in `T`, it is used as-is. |

Returns:
```python
{
  "status": "ok",
  "ticker": "PETR4T",
  "underlying": "PETR4",
  "refdate": "2026-08-21",
  "company": "PETROLEO BRASILEIRO S.A. PETROBRAS",
  "isin": "BRPETRTNP008",
  "security_category": "COMMON EQUITIES FORWARD",
  "specification": "PN      N2",
  "open_interest": 1196,
  "total_quantity": 1358721,
  "forward_price_aggregate": 58828062.67,
  "forward_price_per_share": 43.32,
  "instruments_ok": true
}
```

## Tool Invocation

```python
data_source(domain="b3", sub_domain="api", mode="sync")
data_source(domain="b3", sub_domain="api", mode="sync", params='{"table":"trades"}')
data_source(domain="b3", sub_domain="api", mode="query", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="api", mode="lookup_ticker", params='{"ticker":"PETR4"}')
data_source(domain="b3", sub_domain="api", mode="search_company", params='{"name":"PETROBRAS"}')
# [v2.0] Open positions queries:
data_source(domain="b3", sub_domain="api", mode="open_positions", params='{"underlying":"PETR4"}')
data_source(domain="b3", sub_domain="api", mode="lookup_option_positions", params='{"ticker":"PETRG36"}')
# [v2.1] Forward positions query (term skill fallback):
data_source(domain="b3", sub_domain="api", mode="forward_positions", params='{"ticker":"PETR4"}')
```

---

*Last updated: 2026-08-25 (v2.1 — forward_positions() mode for the term skill's stock-term fallback).*
