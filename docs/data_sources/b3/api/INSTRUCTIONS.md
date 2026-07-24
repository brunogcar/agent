<- Back to [API Overview](../API.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never use the old 3-step CSV download flow** — The token endpoint (`/api/download/requestname`) returns HTTP 400 for all server-side requests. B3 migrated to a paginated JSON API. Use `/tabelas/table/{name}/{date}/{page}`.
2. **Never hardcode column schemas** — The API returns columns dynamically. The sync engine creates columns from the API response.
3. **Never skip the batch commit** — Without `BATCH_SIZE=500` commit intervals, a cancelled sync loses all progress. The resume feature depends on committed pages.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `ThreadPoolExecutor(10 workers)` for concurrent page fetches** — Sequential fetch of 7138 pages takes ~20min; concurrent takes ~2min.
2. **Always use `sync_state` for resume** — Compare `last_page >= page_count` to detect completion (not `row_count > 0`).
3. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

- **v1.0.4 lesson:** Resume bug — `row_count > 0` was treated as "done". Fixed to compare `last_page >= page_count`. Without this, a partial sync (100/7138 pages) would skip the remaining 7038 pages.
