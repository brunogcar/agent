<- Back to [COTAHIST_DERIVATIVES Overview](../COTAHIST_DERIVATIVES.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never create a separate `sync_engine.py` for derivatives** — Derivatives are populated by the STANDARD COTAHIST sync (`data_sources/b3/cotahist/sync_engine.py`). The sync engine writes to BOTH the `cotahist` (equities) + `cotahist_derivatives` tables in one ZIP parse pass, dispatching per-row by BDI code. A separate sync would download + parse the same 765MB TXT twice.
2. **Never declare `cotahist_derivatives` as a separate `REQUIRED_SOURCES` entry** — there is no `sync_map["cotahist_derivatives"]` entry in `skills/_base.py`. The options skill MUST use `REQUIRED_SOURCES = ["cotahist"]` — the cotahist sync guard covers derivatives too.
3. **Never query the `cotahist_derivatives` table without normalizing the underlying** — Every query function MUST strip trailing digits (`"PETR4"` → `"PETR"`). The `underlying` column stores the 4-letter code. Querying `"PETR4"` directly returns 0 rows.
4. **Never parse the option ticker at query time** — `underlying`, `option_type`, `expiration_month`, `strike_parsed` are derived columns parsed ONCE during sync (via `catalog.parse_option_ticker()`) and stored with indexes. Runtime parsing per row would be O(n) string ops on every query.
5. **Never assume the `cotahist_derivatives` table exists** — Always wrap `connect()` in try/except. The table might not exist (first run before sync) or `cotahist.db` might be missing entirely. The query functions return `{"status": "not_synced", "error": ...}` on `FileNotFoundError`, and the calling skill wraps in `_safe_query()` to catch anything else.
6. **Never change the BDI codes {78, 82, 83, 84, 26}** — These are the official B3 BDI codes verified from the COTAHIST layout PDF. 78=CALL, 82=PUT, 83=CALL(index), 84=PUT(index), 26=TERM. Changing them would either drop rows (sync) or query the wrong instruments (query).
7. **Never change the option ticker month-code convention** — Call months A-L (Jan-Dec), Put months M-X (Jan-Dec). This is the B3 standard. `parse_option_ticker()` depends on `_CALL_MONTHS` + `_PUT_MONTHS` dicts that map these exact letters.
8. **Never create `.bak` files** — Forbidden by project rules.
9. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
10. **Never print to stdout in production code** — MCP stdio corruption. Use `core.tracer` if logging is needed.

### ALWAYS DO

1. **Always delegate `db_path()` to the cotahist catalog** — `data_sources/b3/cotahist_derivatives/catalog.db_path()` calls `data_sources.b3.cotahist.catalog.db_path()`. Derivatives share the SAME `cotahist.db` file. Never hardcode a separate path.
2. **Always use `connect(read_only=True)` for queries** — The SQLite URI `file:path?mode=ro` prevents accidental writes. The `connect()` helper in `catalog.py` defaults to read-only.
3. **Always return a `status` field** — Every query function MUST return `{"status": "ok" | "error" | "not_synced" | "not_found", ...}`. Callers (the options skill) depend on this contract to decide between rendering data vs an error section.
4. **Always include the `underlying` field in the response** — Normalized to the 4-letter code. Even on error responses (so the caller can echo it in the error message).
5. **Always sort the options chain by `option_type` then `strike_parsed`** — `ORDER BY option_type, strike_parsed` — calls first (alphabetically `CALL` < `PUT`), then ascending by strike within each group. This is the standard chain layout.
6. **Always run `compileall` before `pytest`** — Catches syntax errors early.
7. **Always re-parse the ticker when adding a new derived column** — If a new derived column is added (e.g., `days_to_maturity`), populate it during sync in `data_sources/b3/cotahist/sync_engine.py` (not at query time). Add the column to `DERIVATIVES_SCHEMA_SQL` + the sync engine's INSERT column list.
8. **Always test the ticker parser with edge cases** — `PETRH36` (simple), `PETRA215` (half-point), `PETRA3650` (4-digit strike), `PETR4` (equity, should return `None`). See `catalog.parse_option_ticker()` docstring.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

---

*Last updated: 2026-08-18 (v1.0).*
