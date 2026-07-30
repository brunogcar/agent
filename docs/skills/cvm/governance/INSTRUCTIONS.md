<- Back to [GOVERNANCE Overview](../GOVERNANCE.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never query CGVN database directly from governance skill** — governance wraps CGVN query_engine. No SQL in governance.py.
2. **Never fail the skill on CGVN not synced** — Return not_synced status. The caller decides what to do.
3. **Never weight practices by chapter** — Score is a simple percentage (Sim / total). Weighting would introduce subjectivity.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only.
6. **Never print to stdout** — MCP stdio corruption.

### ALWAYS DO

1. **Always add data_freshness** — Use `add_freshness(result)` from `_freshness.py`.
2. **Always query latest filing only** — Use MAX(Data_Referencia) to get the most recent governance disclosure.
3. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors.)*

- **v1.1 lesson:** Decomposed monolithic `governance.py` (75 lines) into `_registry.py` + `modes/` + `report.py`. New modes now drop in via `@register_mode(...)` in `modes/<name>.py` with zero edits to `__init__.py`. The `dashboard` mode is a thin pass-through of the per-mode payloads into a multi-tab dashboard dict, mirroring the `financials`/`valuation`/`comparison`/`backtest`/`dividends` dashboard pattern.

---

*Last updated: 2026-07-29 (v1.1).*
