<- Back to [BRAPI Overview](../BRAPI.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never hardcode the ticker list** — Always use `sync_tickers()` to fetch the full list from brapi.dev. The list changes as companies list/delist.
2. **Never skip the rate limiter** — brapi.dev may rate-limit or ban without the 0.5s delay between calls.
3. **Never create `.bak` files** — Forbidden by project rules.
4. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
5. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always try local DB first for quotes** — `quote(force=False)` checks local cache before hitting the API. Only use `force=True` when freshness is critical.
2. **Always convert epoch to YYYY-MM-DD** — brapi.dev returns dates as epoch milliseconds. SQLite needs YYYY-MM-DD for correct sorting.
3. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

---

*Last updated: 2026-07-24 (v1.0).*
