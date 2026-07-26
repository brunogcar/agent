<- Back to [INSIDER Overview](../INSIDER.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never query VLMO database directly from insider skill** — insider wraps VLMO query_engine. No SQL in insider.py.
2. **Never fail the skill on VLMO not synced** — Return not_synced status. The caller decides what to do.
3. **Never create `.bak` files** — Forbidden by project rules.
4. **Never rewrite entire files** — Surgical edits only.
5. **Never print to stdout** — MCP stdio corruption.

### ALWAYS DO

1. **Always add data_freshness** — Use `add_freshness(result)` from `_freshness.py` so callers know data age.
2. **Always uppercase tickers** — `company.strip().upper()` before passing to query_engine.
3. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors.)*

---

*Last updated: 2026-07-25 (v1.0).*
