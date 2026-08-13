<- Back to [PRICE Overview](../PRICE.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic to a skill mode function** — Skills are read-only. Sync belongs in `data_sources/`. The sync GUARD (`ensure_fresh()`) lives in `skills/_base.py` and is wired via `make_route(required_sources=["cotahist"])` in `__init__.py` — it triggers `data_sources.b3.cotahist.sync_engine.sync()` before dispatch, but the skill mode functions themselves never call sync.
2. **Never compute in `report/` builders** — Builders are pure shape: they accept already-computed arrays (closes, MAs, drawdowns, etc.) and emit section dicts. ALL computation belongs in `engines.py`. If a builder needs a derived value (e.g., volume MA20), import the engine function and call it from inside the builder — but the heavy lifting (DB queries, statistics) stays in `engines.py`.
3. **Never call the `data_source()` tool function** — Import the query engines directly (`from skills.b3.price.engines import ohlcv_series, latest_quote`). Avoids JSON round-trip overhead.
4. **Never duplicate engine functions in a builder** — If you need SMA, returns, drawdown, etc., call `compute_sma`, `compute_returns`, `compute_drawdowns` from `engines.py`. Re-implementing them in a builder creates a second source of truth that drifts.
5. **Never assume the cotahist DB is fresh** — Always wire `ensure_fresh()` via `required_sources=["cotahist"]`. Tests must use `CVM_SKIP_SYNC=1` (set in conftest) to bypass.
6. **Never render the candlestick chart without the financial plugin** — The Cotação tab's candlestick chart_data uses `type: "candlestick"` which is NOT a built-in Chart.js type. The `chartjs-chart-financial` CDN script must be loaded in `dashboard.html` (`{% block scripts %}`) before any candlestick canvas renders.
7. **Never create `.bak` files** — Forbidden by project rules.
8. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
9. **Never print to stdout in production code** — MCP stdio corruption. The `[b3.price]` log lines are exceptions because they're flushed + go to stderr in the MCP context (the agent stack routes them via `core.tracer`). If unsure, use `core.tracer`.

### ALWAYS DO

1. **Always declare `REQUIRED_SOURCES = ["cotahist"]` in `__init__.py`** — Sync guard checks freshness before each dispatch + force-syncs if stale. Tests use `CVM_SKIP_SYNC=1` (set in conftest). Per-call bypass: `route(..., skip_sync=True)`.
2. **Always use the modular `modes/ + _registry.py` pattern** — Adding a new mode = drop a file in `modes/` + `@register_mode(...)`. No edits to `__init__.py` or `_registry.py`. Delegates to `skills/_base.py` (shared infrastructure with all 14 skills).
3. **Always keep computation in `engines.py`** — Report builders must accept already-computed values as parameters. If a new indicator is needed, add it to `engines.py` first, then pass its output to the relevant builder.
4. **Always set `price_range_selector: true` on every chart section** that uses a date axis — The 7-button range selector (Tudo/10A/5A/1A/6M/3M/1M) is the standard pattern for any time-series chart. Without it, users can't zoom into shorter windows.
5. **Always include `price_full_labels`, `price_full_datasets`, `price_full_data`** when using `price_range_selector` — The `filterPriceChart()` JS reads these to filter the chart client-side. Missing any of these three fields means the filter buttons do nothing.
6. **Always color volume bars by up/down day** — Green (`#22c55e`) if `close >= open`, red (`#ef4444`) otherwise. This is the convention in `report/cotacao.py` + `report/volume.py`. Don't deviate without good reason.
7. **Always return `kpis` + `tabs` in the dashboard response** — Even on partial failure, the structure must stay intact (KPIs as "—" with error message). The HTML dashboard must always render.
8. **Always run `compileall` before `pytest`** — Catches syntax errors early.
9. **Always split tests by mode** — `test_dashboard.py` / `test_route.py` + shared `conftest.py`. One test class per file.
10. **Always mock the cotahist DB in tests** — Use the `price_env` fixture from `conftest.py`. Never hit the real DB in tests (it's 1-2 GB and changes daily). The fixture builds a 10-row synthetic DB that exercises every engine path.
11. **Always keep MA line colors consistent** — MA20=#facc15 (yellow), MA50=#fb923c (orange), MA100=#ec4899 (pink), MA200=#ef4444 (red). These are defined in `report/cotacao.py` and `report/medias.py` — keep them in sync.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

---

*Last updated: 2026-08-06 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
