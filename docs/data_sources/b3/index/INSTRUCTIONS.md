<- Back to [INDEX Overview](../INDEX.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never sync all 26 catalogued indices by default** — Only `ACTIVE_INDICES` (5: IBOV, SMLL, BDRX, IFIX, IDIV) should be synced by `sync_all()`. Catalog-only indices require explicit `sync_index(index=...)`.
2. **Never DELETE without re-INSERT in the same transaction** — Each per-index sync is DELETE + INSERT (idempotent). A DELETE without the matching INSERT leaves the DB in an inconsistent state.
3. **Never store weights as percentages (0-100)** — Always normalize to 0.0–1.0 (divide by 100). B3 returns "5.23" meaning 5.23%.
4. **Never trust `weight` as a tie-breaker for `position`** — B3 sometimes returns equal weights; `position` is the authoritative rank.
5. **Never create `.bak` files** — Forbidden by project rules.
6. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
7. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use the base64-encoded payload for B3 index API calls** — `base64({"symbol":"IBOV","language":"pt-br"})`. The API returns HTTP 400 for un-encoded JSON.
2. **Always normalize dates to YYYY-MM-DD** — B3 returns DD/MM/YYYY. Convert at ingest for correct SQLite sorting.
3. **Always record `last_synced_at` on the `indices` row** — The sync guard (`ensure_fresh()`) reads this column to decide whether to force-sync.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

---

*Last updated: 2026-08-05 (v1.0).*
