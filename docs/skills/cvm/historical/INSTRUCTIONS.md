<- Back to [HISTORICAL Overview](../HISTORICAL.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never compute TTM for each day individually** — TTM changes only quarterly. Use `ttm_earnings_periods()` to get the step function, then do O(1) lookups per day.
2. **Never forget parse_escala** — DFP/ITR store raw values with escala ("MIL", "MILHOES"). Always apply `parse_escala(r["escala"])` before using values.
3. **Never return P/L when earnings <= 0** — P/L is meaningless with negative earnings. Return None (chart shows gaps).
4. **Never hardcode empresa_ids** — DFP and ITR have independent autoincrement IDs. Always call `resolve_company()` separately for each database.
5. **Never create `.bak` files** — Forbidden by project rules.
6. **Never rewrite entire files** — Surgical edits only.
7. **Never print to stdout** — MCP stdio corruption.

### ALWAYS DO

1. **Always resolve empresa_ids separately for DFP and ITR** — They are separate SQLite files with independent autoincrement IDs. Using DFP's IDs to query ITR returns wrong/empty rows.
2. **Always use step-function optimization** — Precompute TTM earnings periods + shares periods, then lookup per day. Don't recompute TTM for 1200 days.
3. **Always add data_freshness** — Use `add_freshness(result)` from `_freshness.py`.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors.)*

---

*Last updated: 2026-07-25 (v1.0).*
