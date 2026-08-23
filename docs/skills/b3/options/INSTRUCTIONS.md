<- Back to [OPTIONS Overview](../OPTIONS.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic to the options skill** — Skills are read-only. Sync belongs in `data_sources/`. The `cotahist_derivatives` table is populated by the STANDARD cotahist sync pass (same ZIP parse writes to both the equities + derivatives tables). The sync guard (`ensure_fresh(["cotahist"])`) is wired via `make_route()` in `__init__.py`. Never call any sync function from the skill layer.
2. **Never declare `REQUIRED_SOURCES = ["cotahist_derivatives"]`** — there is NO separate sync function for derivatives. The `cotahist_derivatives` table rides on the cotahist sync. Declaring a separate source would make `ensure_fresh()` look for a `sync_map` entry that doesn't exist and crash. Always use `REQUIRED_SOURCES = ["cotahist"]`.
3. **Never compute aggregation in the skill layer** — All `SUM(CASE WHEN option_type='CALL'...)` aggregation happens in SQL inside `cotahist_derivatives.query_engine`. The skill layer is pure shape: query → format → emit section dicts. If a new metric is needed (e.g., IV), add the math to a new `engines.py` (see ROADMAP P1) — but the SQL aggregation for volume/ratio stays in `query_engine.py`.
4. **Never call the `data_source()` tool function** — Import the query engines directly (`from data_sources.b3.cotahist_derivatives.query_engine import options_chain, put_call_ratio, volume_by_strike`). Avoids JSON round-trip overhead.
5. **Never assume the `cotahist_derivatives` table exists** — Always wrap each query in `_safe_query()`. The table might not exist (first run before sync) or the DB might be missing entirely. The `_safe_query()` wrapper normalizes all failures into `{status: "error", error: <msg>}` so the dashboard stays `status=ok` with error sections (graceful-degradation contract).
6. **Never deviate from the call/put color convention** — Calls = green (`#22c55e`), Puts = red (`#ef4444`), P/C reference line at 1.0 = dashed grey (`#9ca3af`). These are defined in `report.py` (`_COLOR_CALL`, `_COLOR_PUT`) and `modes/dashboard.py` (`_COLOR_REF`). The Volume por Strike bar chart MUST use both colors (calls + puts side by side).
7. **Never forget to normalize the underlying** — `_normalize_underlying("PETR4")` → `"PETR"` (strip trailing digits). The `cotahist_derivatives` table is keyed on the 4-letter code, NOT the full ticker. The query engine also normalizes defensively, but the skill MUST normalize so the response's `underlying` field is the clean code.
8. **Never create `.bak` files** — Forbidden by project rules.
9. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
10. **Never print to stdout in production code** — MCP stdio corruption. The `[b3.options]` log lines are exceptions because they're flushed + go to stderr in the MCP context. If unsure, use `core.tracer`.

### ALWAYS DO

1. **Always declare `REQUIRED_SOURCES = ["cotahist"]` in `__init__.py`** — NOT `["cotahist_derivatives"]`. The derivatives table shares the cotahist DB. The sync guard triggers the cotahist sync if stale; derivatives ride along.
2. **Always use the modular `modes/ + _registry.py` pattern** — Adding a new mode = drop a file in `modes/` + `@register_mode(...)`. No edits to `__init__.py` or `_registry.py`. Delegates to `skills/_base/` (shared infrastructure with all 23 skills).
3. **Always wrap each query in `_safe_query()`** — Catches `FileNotFoundError` (DB missing), `sqlite3.OperationalError` (table missing), `RuntimeError` (config error). Emits an error section on failure so the dashboard stays `status=ok` (graceful-degradation contract).
4. **Always set `price_range_selector: true` on every chart section** that uses a date axis — The 7-button range selector (Tudo/10A/5A/1A/6M/3M/1M) is the standard pattern for any time-series chart. The P/C ratio chart needs it; the Volume por Strike bar chart includes it for consistency (even though it's a single-day snapshot).
5. **Always include `price_full_labels`, `price_full_datasets`, `price_full_data`** when using `price_range_selector` — The `filterPriceChart()` JS reads these to filter the chart client-side. Missing any of these three fields means the filter buttons do nothing.
6. **Always return `tabs` in the dashboard response** — Even on full failure (missing DB), the structure must stay intact with error sections. The HTML dashboard must always render.
7. **Always run `compileall` before `pytest`** — Catches syntax errors early.
8. **Always keep the option ticker legend in the Cadeia de Opções tab** — The `_LEGEND_BODY` text section is always emitted first (before the chain table) so users understand the ticker convention (Call months A-L, Put months M-X, strike half-point rule `215` → 21,50).
9. **Always sort the options chain by `option_type` then `strike_parsed`** — Calls first (sorted by strike ascending), then puts (sorted by strike ascending). This matches the `query_engine.options_chain` ORDER BY clause and is the standard chain layout.
10. **Always pick the nearest maturity when none is specified** — `options_chain` / `volume_by_strike` auto-select the nearest future expiration (or the most recent past one if no future maturities exist). Don't change this without surfacing a maturity-selector UI widget first.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

---

*Last updated: 2026-08-18 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
