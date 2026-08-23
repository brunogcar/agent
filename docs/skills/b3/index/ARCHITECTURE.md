<- Back to [INDEX Overview](../INDEX.md)

# 🏗️ Architecture — index skill

## Purpose

Combines B3 INDEX data with light domain reasoning to answer common index questions:
- "What's in IBOV?" (dashboard)
- "How does IBOV compare to SMLL?" (compare)
- "Which indices include PETR4?" (ticker)

## 🔗 Source Code Reference

```text
skills/b3/index/
├── __init__.py        MANIFEST + route() dispatch (auto-discovery) + REQUIRED_SOURCES=["index"]
├── _registry.py       ModeSpec + register_mode + MODES dict (delegates to skills/_base/)
├── helpers.py         compute_jaccard, compute_sector_breakdown, compute_returns, format_pct
├── report.py          dashboard section builders (KPI cards, constituent table, sector chart, history line)
└── modes/             one file per mode, auto-discovered via importlib
    ├── __init__.py    minimal package marker
    ├── dashboard.py   @register_mode("dashboard") — single-index deep dive (default)
    ├── compare.py     @register_mode("compare")    — side-by-side multi-index comparison
    └── ticker.py      @register_mode("ticker")     — reverse-lookup: ticker → indices
```

### Test module tree

```text
tests/skills/b3/index/
├── conftest.py        index_env fixture — synthetic index.db (IBOV + SMLL)
├── test_dashboard.py  TestDashboardMode (4 tests — KPI cards, tabs, charts)
├── test_compare.py    TestCompareMode (3 tests — overlap, performance, sectors)
├── test_ticker.py     TestTickerMode (2 tests — single index, multi index)
└── test_route.py      TestIndexRoute (2 tests — mode dispatch + sync guard)
```

11 tests total (v1.0).

## Data Flow

```
skill(domain="b3", sub_domain="index", mode="dashboard", params='{"index":"IBOV"}')
  │
  ▼  ensure_fresh(["index"])  ← route() wrapper, sync guard
  │  1. Check index.indices.last_synced_at < 24h
  │  2. If stale → call sync_all() (5 active indices, ~30s)
  │
  ▼  dashboard mode
  │  1. Fetch IBOV composition (constituents table)
  │  2. Fetch IBOV history (history table, last 365 days)
  │  3. Build KPI cards (constituent count, latest close, 1Y return, top-10 weight)
  │  4. Build top-N constituents table + weight doughnut chart
  │  5. Build historical close line chart
  │  6. Build sector breakdown (join with B3 API instruments for segment)
```

## Modes

| Mode | Default | Source | Returns |
|------|---------|--------|---------|
| `dashboard` | top_n=10, history_days=365 | INDEX (composition + history) + API instruments (segment) | 4-tab dashboard payload (Overview / Constituents / History / Sectors) |
| `compare` | history_days=365 | INDEX (multiple indices) + API instruments (segment) | 3-tab dashboard (Performance / Overlap / Sectors) |
| `ticker` | — | INDEX (constituents reverse-lookup) | Single-section response: list of indices containing the ticker + weight |

## Sync Guard (v1.0)

`REQUIRED_SOURCES = ["index"]` wired via `make_route()`.

- `route()` calls `ensure_fresh()` before each dispatch — checks `index.indices.last_synced_at`.
- If stale (> 24h) or missing, triggers `sync_all()` (5 active indices).
- Re-entrancy guard: nested `route()` calls (e.g., dashboard composes multiple internal queries) trigger `ensure_fresh()` at most once.
- Escape hatches: `B3_SKIP_SYNC=1` env var (set in conftest for tests) + `route(..., skip_sync=True)` kwarg.
- Failure path: sync failure proceeds with stale data + error in `result["_sync"]["errors"]`. Stale-but-available is better than no answer for a dashboard use case.

---

*Last updated: 2026-08-05 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
