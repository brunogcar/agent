<- Back to [INSIDER Overview](../INSIDER.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never query VLMO database directly from insider skill** — insider wraps VLMO query_engine. No SQL in insider.py / modes/*.py.
2. **Never fail the skill on VLMO not synced** — Return not_synced status. The caller decides what to do.
3. **Never create `.bak` files** — Forbidden by project rules.
4. **Never rewrite entire files** — Surgical edits only.
5. **Never print to stdout** — MCP stdio corruption.

### ALWAYS DO

1. **Always add data_freshness** — Use `add_freshness(result)` from `_freshness.py` so callers know data age.
2. **Always uppercase tickers** — `company.strip().upper()` before passing to query_engine.
3. **Always run `compileall` before `pytest`** — Catches syntax errors early.
4. **Always register new modes via `@register_mode(...)`** — Drop a file in `modes/` + decorate. No edits to `__init__.py` or `_registry.py` needed (auto-discovery picks them up).
5. **Always keep `dashboard` mode a thin composition** — `dashboard()` calls `summary()` / `history()` / `by_role()` and reshapes their output via `report.py` builders. Each sub-call must be independently `try/except`-wrapped so partial failures degrade gracefully (table with 0 rows, KPIs as "—") instead of crashing the whole dashboard.

---

### Anti-patterns & Lessons Learned

- **[v1.1] Modular split + dashboard composition**: Split the 91-line `insider.py` monolith into the standard CVM modular structure (`_registry.py` + `modes/{history,by_role,summary,dashboard}.py` + `report.py` + auto-discovery in `__init__.py`). Mirrors the governance v1.1 / shareholders v1.1 / screener v1.4 split pattern. `insider.py` deleted — no backward-compat re-exports needed (only the test file imported it, already updated). The new `dashboard` mode (4 tabs + 4 KPI cards) is a thin composition of `summary()` + `history(company, limit=10)` + `by_role()` — it does NOT fetch new data, just reshapes existing mode outputs. The new `report.py` pre-formats KPI values via `apply_fmt` so the `insider_dashboard` adapter passes them through verbatim (only re-formats raw numbers when needed). All 26 insider tests pass (11 original incl. 1 NEW route dispatch test + 15 NEW TestDashboardMode) + 11 NEW TestInsiderDashboardAdapter tests pass.
- **[v1.0] Initial implementation**: 3 modes (history / by_role / summary) wrap VLMO query_engine with bridge resolution + data freshness. Summary computes overall sentiment (buying/selling/neutral) + net_volume = total_bought - total_sold. Read-only — no sync.
- **v2.0 lesson:** _registry.py + __init__.py now delegate to `skills/_base/` (shared ModeSpec + make_registry + make_route + auto_discover_modes). The duplicated ~97-line _registry.py + ~88-line __init__.py boilerplate is gone — each skill's _registry.py is now ~16 lines, __init__.py is ~50 lines. Adding a new mode = drop a file in `modes/` + `@register_mode(...)` (unchanged). Adding a new skill = 3 files (_registry.py + __init__.py + modes/) following the pattern in [SKILLS.md → How to Create a New Skill](../../SKILLS.md). Bug fixes to the dispatch infrastructure now only need to be made in ONE place.

---

*Last updated: 2026-07-30 (v2.0).*
