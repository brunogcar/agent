<- Back to [SHAREHOLDERS Overview](../SHAREHOLDERS.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic to a skill** — Skills are read-only. They call data_source query engines. Sync belongs in `data_sources/`.
2. **Never call the `data_source()` tool function** — Import the query engines directly (e.g., `from data_sources.cvm.fre.query_engine import shareholders`). Avoids JSON round-trip overhead.
3. **Never use `float(escala)` directly** — DFP stores escala as Portuguese words ("MIL", "MILHOES"). Always use `parse_escala()` from `_db.py`.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `parse_escala()` for escala values** — v1.0.1 fix. `float("MIL")` crashes.
2. **Always make summary sections best-effort** — If one data source is missing, the summary should still return what's available (not fail entirely).
3. **Always accept `company` (ticker/name/CNPJ) in all modes** — The resolver + bridge handle resolution. Don't restrict to tickers only.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.
5. **Always use `@register_mode(...)` for new modes (v1.1)** — Drop a file in `modes/` + decorate; no edits to `__init__.py` or `_registry.py` needed (auto-discovery via importlib).

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

- **v1.0.1 lesson:** `equity_structure` mode crashed with `could not convert string to float: 'MIL'` — DFP stores ESCALA_MOEDA as Portuguese words. Fix: use `parse_escala()`.
- **v1.1 lesson:** Decomposed monolithic `shareholders.py` (233 lines) into `_registry.py` + `modes/` + `report.py`. New modes now drop in via `@register_mode(...)` in `modes/<name>.py` with zero edits to `__init__.py`. The `dashboard` mode is a thin pass-through of the `summary()` result into a 4-tab dashboard dict (Overview / Top Shareholders / Free Float / Equity Structure), mirroring the `financials`/`valuation`/`comparison`/`backtest`/`dividends`/`governance`/`historical`/`screener` dashboard pattern. The summary mode's sibling-mode imports use aliased names (`from ...modes.shareholders import shareholders as _shareholders`) to avoid name clash with the `summary` mode name + to keep call sites short.

---

*Last updated: 2026-07-30 (v1.1).*
