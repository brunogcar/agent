<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🏗️ Architecture — options skill

## Purpose

Single-underlying options analytics from the B3 COTAHIST derivatives table.
Three tabs:
1. **Cadeia de Opções** — legend + options chain table (calls then puts,
   each sorted by strike)
2. **Put/Call Ratio** — daily P/C ratio line chart (90-day window) with a
   dashed grey reference line at 1.0 + latest 15 observations table
3. **Volume por Strike** — 2-dataset bar chart (calls vs puts volume) for
   the nearest maturity + detail table

## 🔗 Source Code Reference

```text
skills/b3/options/
├── __init__.py        MANIFEST + route() dispatch (auto-discovery)
│                      + REQUIRED_SOURCES=["cotahist"] (shared DB)
├── _registry.py       MODES dict + register_mode (delegates to skills/_base/)
├── helpers.py         format_value, format_brl, format_int (pure functions,
│                      PT-BR convention; adds "ratio" unit for P/C ratio)
├── report.py          Section builders: build_kpi_card, build_chart_section,
│                      build_table_section, build_text_section, build_error_section
└── modes/             one file per mode, auto-discovered via importlib
    ├── __init__.py    minimal package marker
    └── dashboard.py   @register_mode("dashboard") — 3-tab deep dive (default)
```

> **No `engines.py`** — unlike the price skill (which has heavy math: SMA,
> RSI, MACD, Bollinger Bands), the options skill does no computation. All
> aggregation (`SUM(CASE WHEN option_type='CALL'...)`) happens in SQL
> inside the `cotahist_derivatives.query_engine` functions. The skill
> layer is pure shape: query → format → emit section dicts.

### Test module tree

```text
tests/skills/b3/options/
└── (planned — see ROADMAP)
```

## Data Flow

```
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR4"}')
  │
  ▼  ensure_fresh(["cotahist"])  ← route() wrapper, sync guard
  │  1. Check cotahist sync_state.last_synced_at < 24h
  │  2. If stale → call sync(year=current_year) (~30s)
  │     (the same sync populates BOTH equities + cotahist_derivatives tables)
  │
  ▼  dashboard mode (modes/dashboard.py)
  │  1. Normalize underlying: "PETR4" → "PETR" (strip trailing digits)
  │  2. _build_chain_tab(u)         → options_chain(u)  [nearest maturity]
  │  3. _build_put_call_ratio_tab(u, days=90)
  │                                  → put_call_ratio(u, days=90)
  │  4. _build_volume_by_strike_tab(u)
  │                                  → volume_by_strike(u)  [nearest maturity]
  │  5. Each query wrapped in _safe_query() — any connect() failure
  │     (missing DB, missing table, config error) → error section
  │     instead of crashing the whole dashboard.
  │  6. Build 3 tabs: Cadeia de Opções / Put/Call Ratio / Volume por Strike
  │  7. Return {status, underlying, title, tabs}
  │
  ▼  _auto_generate_html()  ← writes PETR_options_dashboard.html
```

## Query Engine Inventory (`data_sources.b3.cotahist_derivatives.query_engine`)

The skill calls these functions directly (no JSON round-trip):

| Function | Returns | Notes |
|----------|---------|-------|
| `options_chain(underlying, maturity="", limit=200)` | `{status, underlying, maturity, refdate, count, options: [...]}` | Nearest maturity if `maturity` empty. Calls first (sorted by strike), then puts. Each option row has: `symbol, bdi_code, option_type, strike, strike_parsed, maturity, close, volume, best_bid, best_ask, refdate`. |
| `available_maturities(underlying)` | `{status, underlying, maturities: [{maturity, count}]}` | All distinct expiration dates, ascending. (Not yet surfaced in the dashboard — reserved for a future maturity-selector widget.) |
| `put_call_ratio(underlying, days=90)` | `{status, underlying, count, observations: [{ref_date, call_volume, put_volume, ratio}]}` | `ratio = put_vol / call_vol`. `None` when `call_vol == 0`. Ascending by date. |
| `volume_by_strike(underlying, maturity="")` | `{status, underlying, maturity, refdate, count, strikes: [...]}` | Per-strike aggregation for the latest trading day. Each strike: `{strike, call_volume, put_volume, call_count, put_count}`. Ascending by strike. |

### Status codes returned by every query function

| Status | Meaning | Dashboard handling |
|--------|---------|--------------------|
| `ok` | Success — data returned | Render the tab sections |
| `error` | Caller error (missing/invalid `underlying`) | Error section (shouldn't happen post-normalization) |
| `not_synced` | `cotahist.db` doesn't exist (`FileNotFoundError`) | Error section ("run sync first") |
| `not_found` | No options for this underlying / maturity | Error section ("nenhuma opção encontrada") |

The dashboard's `_safe_query()` wrapper also catches any other exception
(`RuntimeError` from config, `sqlite3.OperationalError` for a missing
table) and normalizes it into `{status: "error", error: <msg>}` so the
dashboard stays `status=ok` with error sections.

## Design Decisions

- **No `engines.py`** — the options skill does no client-side math. All
  aggregation (sum by date, sum by strike, put/call ratio) happens in SQL
  inside `query_engine.py`. The skill layer is pure shape. This mirrors the
  bcb/macro skill (which delegates to the SGS query engine) and differs
  from the price skill (which has a heavy `engines.py`).
- **`REQUIRED_SOURCES = ["cotahist"]` (not a separate source)** — the
  `cotahist_derivatives` table lives in the SAME `cotahist.db` as the
  equities table, and is populated during the SAME COTAHIST sync pass (the
  sync engine writes to both tables row-by-row). Declaring a separate
  `"cotahist_derivatives"` source would require a separate sync function
  that doesn't exist. The cotahist sync guard covers derivatives too.
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
- **Graceful degradation contract** — a failing sub-query never crashes
  the dashboard. Each tab builder wraps its query in `_safe_query()` and
  emits an error section on failure. The other tabs still render. This
  mirrors the CVM financials + bcb/macro contract.

---

*Last updated: 2026-08-18 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
