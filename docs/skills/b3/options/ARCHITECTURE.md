<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🏗️ Architecture — options skill

## Purpose

Single-underlying options analytics from the B3 COTAHIST derivatives table +
the B3 API CSV bulk download (DerivativesOpenPosition + InstrumentsConsolidated).
Six tabs:
1. **Cadeia de Opções** — legend + options chain table (calls then puts,
   each sorted by strike) + [v1.3] OI/Coberta/Descoberta columns from
   derivatives.db.
2. **Put/Call Ratio** — daily P/C ratio line chart (90-day window) with a
   dashed grey reference line at 1.0 + latest 15 observations table.
3. **Volume por Strike** — 2-dataset bar chart (calls vs puts volume) for
   the nearest maturity + detail table.
4. **Exercicios** — daily exercise of stock options (BDI 38/42) chart + table.
5. **Volatilidade Implícita** — IV smile chart + IV table + IV term heatmap
   (Black-Scholes + Selic from BCB SGS).
6. **Posições em Aberto** — [v1.3] Open Interest by Strike bar chart + CALL
   vs PUT summary (Coberta/Travada/Descoberta/Total/Titulares/Lançadores)
   + per-option detail table with strike + expiration + days_to_expiration.
   Uses the B3 API CSV bulk download (`derivatives.db` 17 cols joined with
   `instruments.db` 52 cols on TckrSymb).

## 🔗 Source Code Reference

```text
skills/b3/options/
├── __init__.py        MANIFEST + route() dispatch (auto-discovery)
│                      + REQUIRED_SOURCES=["cotahist", "sgs",
│                      "b3-api-derivatives", "b3-api-instruments"]
├── _registry.py       MODES dict + register_mode (delegates to skills/_base/)
├── helpers.py         format_value, format_brl, format_int (pure functions,
│                      PT-BR convention; adds "ratio" unit for P/C ratio)
├── engines.py         [v1.2] Black-Scholes pricing + implied_vol
├── report.py          Section builders: build_kpi_card, build_chart_section,
│                      build_table_section, build_text_section, build_error_section
└── modes/             one file per mode, auto-discovered via importlib
    ├── __init__.py    minimal package marker
    └── dashboard.py   @register_mode("dashboard") — 6-tab deep dive (default)
```

> **`engines.py` (v1.2)** — added for the IV tab (Black-Scholes pricing +
> implied_vol: pure Python, no scipy/numpy). The options skill does most of
> its aggregation in SQL inside `cotahist_derivatives.query_engine` (P/C
> ratio, volume by strike, exercise summary) and now also in
> `b3.api.query_engine.open_positions()` (open interest + position breakdown
> via the B3 API CSV bulk download).

### Test module tree

```text
tests/skills/b3/options/
├── conftest.py            Synthetic cotahist.db + sgs.db + b3/derivatives.db
│                          + b3/instruments.db (v1.3) for the 6-tab dashboard.
├── test_dashboard.py      4 tests: no-underlying error + 6-tab structure +
│                          open-positions chart/tables + chain OI columns.
├── test_engines.py        7 Black-Scholes tests (parity, IV round-trip, etc.).
└── test_route.py          route() dispatch tests.

tests/data_sources/b3/api/
├── test_api_query.py             Pre-existing instruments + trades tests.
└── test_api_open_positions.py    [v1.3] 13 tests for open_positions() +
                                 lookup_option_positions() (basic, summary,
                                 by_strike, detail join, zero-position
                                 filter, FORWARD filter, not_found, etc.).
```

## Data Flow

```
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR4"}')
  │
  ▼  ensure_fresh(["cotahist", "sgs", "b3-api-derivatives", "b3-api-instruments"])
  │  ← route() wrapper, sync guard
  │  1. Check each source's sync_state.last_synced_at < 24h
  │  2. If stale → call the source's sync function (~30s cotahist, ~1-3s B3 API CSV)
  │     (cotahist sync populates BOTH equities + cotahist_derivatives tables;
  │      b3-api-derivatives sync populates b3/derivatives.db;
  │      b3-api-instruments sync populates b3/instruments.db)
  │
  ▼  dashboard mode (modes/dashboard.py)
  │  1. Normalize underlying: "PETR4" → "PETR" (strip trailing digits)
  │  2. _build_chain_tab(u)         → options_chain(u)  [nearest maturity]
  │                                  + open_positions(u)  [v1.3: OI/Coberta/Descoberta]
  │  3. _build_put_call_ratio_tab(u, days=90)
  │                                  → put_call_ratio(u, days=90)
  │  4. _build_volume_by_strike_tab(u)
  │                                  → volume_by_strike(u)  [nearest maturity]
  │  5. _build_exercise_tab(u, days=90)
  │                                  → exercise_summary(u, days=90)
  │  6. _build_iv_tab(u)            → Black-Scholes IV per option (Selic from sgs.db)
  │  7. _build_open_positions_tab(u) → open_positions(u)  [v1.3: B3 API CSV bulk]
  │  8. Each query wrapped in _safe_query() — any connect() failure
  │     (missing DB, missing table, config error) → error section
  │     instead of crashing the whole dashboard.
  │  9. Build 6 tabs + return {status, underlying, title, tabs}
  │
  ▼  _auto_generate_html()  ← writes PETR_options_dashboard.html
```

## Query Engine Inventory

The skill calls these functions directly (no JSON round-trip):

### `data_sources.b3.cotahist.derivatives_query` (cotahist.db)

| Function | Returns | Notes |
|----------|---------|-------|
| `options_chain(underlying, maturity="", limit=200)` | `{status, underlying, maturity, refdate, count, options: [...]}` | Nearest maturity if `maturity` empty. Calls first (sorted by strike), then puts. Each option row has: `symbol, bdi_code, option_type, strike, strike_parsed, maturity, close, volume, best_bid, best_ask, refdate`. |
| `available_maturities(underlying)` | `{status, underlying, maturities: [{maturity, count}]}` | All distinct expiration dates, ascending. |
| `put_call_ratio(underlying, days=90)` | `{status, underlying, count, observations: [{ref_date, call_volume, put_volume, ratio}]}` | `ratio = put_vol / call_vol`. |
| `volume_by_strike(underlying, maturity="")` | `{status, underlying, maturity, refdate, count, strikes: [...]}` | Per-strike aggregation for the latest trading day. |
| `exercise_summary(underlying, days=90)` | `{status, underlying, count, observations: [...]}` | BDI 38=call exercise, 42=put exercise. |

### `data_sources.b3.api.query_engine` (b3/derivatives.db + b3/instruments.db)

[v1.3] NEW — uses the B3 API CSV bulk download (DerivativesOpenPosition +
InstrumentsConsolidated). Joined on TckrSymb in Python (SQLite can't JOIN
across DBs without ATTACH).

| Function | Returns | Notes |
|----------|---------|-------|
| `open_positions(underlying)` | `{status, underlying, refdate, instruments_ok, count, summary, by_strike, detail}` | Filters: SgmtNm in (EQUITY CALL, EQUITY PUT); skips rows with OpnIntrst=0 AND TtlPos=0. Joins instruments.db for strike/expiration/style. Graceful: if instruments.db missing, returns degraded (strike=None). |
| `lookup_option_positions(ticker)` | `{status, ticker, oi, var_oi, covered, blocked, uncovered, total, holders, writers, forward}` | Lighter single-ticker lookup (used to enrich chain rows). |

### `data_sources.bcb.sgs.query_engine` (sgs.db)

| Function | Returns | Notes |
|----------|---------|-------|
| `last_value(code)` | `{status, value, ref_date, ...}` | Used by the IV tab to fetch the Selic rate (series 432 = "Meta Selic Copom"). |

### Status codes returned by every query function

| Status | Meaning | Dashboard handling |
|--------|---------|--------------------|
| `ok` | Success — data returned | Render the tab sections |
| `error` | Caller error (missing/invalid `underlying`) | Error section (shouldn't happen post-normalization) |
| `not_synced` | DB doesn't exist (`FileNotFoundError`) | Error section ("run sync first") |
| `not_found` | No options for this underlying / maturity | Error section ("nenhuma opção encontrada") |

The dashboard's `_safe_query()` wrapper also catches any other exception
(`RuntimeError` from config, `sqlite3.OperationalError` for a missing
table) and normalizes it into `{status: "error", error: <msg>}` so the
dashboard stays `status=ok` with error sections.

## Design Decisions

- **`engines.py` (v1.2)** — added for the IV tab (Black-Scholes pricing +
  implied_vol). The other tabs do their aggregation in SQL (P/C ratio,
  volume by strike, exercise summary, open positions).
- **`REQUIRED_SOURCES = ["cotahist", "sgs", "b3-api-derivatives",
  "b3-api-instruments"]`** — the cotahist_derivatives + equities tables
  share `cotahist.db` (one sync pass); the Selic rate is in `sgs.db`; the
  open positions data is in `b3/derivatives.db` + `b3/instruments.db`
  (B3 API CSV bulk download — separate sync per table). All four sources
  are force-synced by the sync guard if any is stale.
- **Underlying normalization in the skill, not the query engine** — both
  layers strip trailing digits (`"PETR4"` → `"PETR"`). The skill does it
  once (so the response `underlying` field is normalized), and the query
  engine does it again defensively (so direct callers don't have to).
- **Accent colors: Calls = green, Puts = red** — matches the universal
  options convention (calls = bullish = green, puts = bearish = red). The
  P/C ratio line is green; the reference line at 1.0 is dashed grey.
- **Nearest maturity auto-selection** — if the caller doesn't specify a
  maturity, `options_chain` / `volume_by_strike` pick the nearest future
  expiration date (or the most recent past one if no future maturities
  exist). This gives the user a sensible default without a UI selector.
- **Open positions Python-side join (v1.3)** — SQLite can't JOIN across
  DBs without ATTACH, so `open_positions()` loads the instruments.db into
  a Python dict (TckrSymb → metadata) and joins each derivatives.db row
  in Python. Graceful degradation: if instruments.db is missing, returns
  derivatives data with strike=None / days_to_expiration=None.
- **Graceful degradation contract** — a failing sub-query never crashes
  the dashboard. Each tab builder wraps its query in `_safe_query()` and
  emits an error section on failure. The other tabs still render. This
  mirrors the CVM financials + bcb/macro contract.

---

*Last updated: 2026-09-08 (v1.3 — Posições em Aberto tab + Cadeia de Opções OI enrichment). See [CHANGELOG.md](CHANGELOG.md) for version history.*
