<- Back to [INDEX Overview](../INDEX.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic to a skill mode function** — Skills are read-only. Sync belongs in `data_sources/`. **[v1.0 exception]** The sync GUARD (`ensure_fresh()`) lives in `skills/_base/sync_guard.py` and is wired via `make_route(required_sources=["index"])` in `__init__.py` — it triggers `data_sources.b3.index.sync_engine.sync_all()` before dispatch, but the skill mode functions themselves never call sync.
2. **Never call the `data_source()` tool function** — Import the query engines directly (e.g., `from data_sources.b3.index.query_engine import index, history, ticker`). Avoids JSON round-trip overhead.
3. **Never assume a ticker belongs to an active index** — The `ticker` mode must return indices from the full catalog (26), not just `ACTIVE_INDICES` (5). A ticker may appear in catalog-only indices like IGC, ISE, etc.
4. **Never compute returns without rebalance awareness** — Index returns include both price changes AND rebalance effects. For >1Y comparisons, prefer the `history.close` series and document that returns are price-only (not total return).
5. **Never create `.bak` files** — Forbidden by project rules.
6. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
7. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always declare `REQUIRED_SOURCES = ["index"]` in `__init__.py`** — Sync guard checks freshness before each dispatch + force-syncs if stale. Tests use `B3_SKIP_SYNC=1` (set in conftest). Per-call bypass: `route(..., skip_sync=True)`.
2. **Always use the modular `modes/ + _registry.py` pattern** — Adding a new mode = drop a file in `modes/` + `@register_mode(...)`. No edits to `__init__.py` or `_registry.py`. Delegates to `skills/_base/` (shared infrastructure with all 23 skills).
3. **Always make dashboard sections best-effort** — If the sector breakdown fails (e.g., B3 API instruments not synced), the dashboard should still return the other tabs with the failed tab degraded to an error text section.
4. **Always return `kpis` + `tabs` in the dashboard response** — Even on partial failure, the structure must stay intact (KPIs as "—" with error message in Overview text). The HTML dashboard must always render.
5. **Always run `compileall` before `pytest`** — Catches syntax errors early.
6. **Always split tests by mode** — `test_dashboard.py` / `test_compare.py` / `test_ticker.py` / `test_route.py` + shared `conftest.py`. One test class per file.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

---

*Last updated: 2026-08-05 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
