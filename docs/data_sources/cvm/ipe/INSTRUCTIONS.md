<- Back to [IPE Overview](../IPE.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never change `_resolve_via_bridge()` tuple unpacking** — It returns `(cnpj, cd_cvm)`. The `query()` function unpacks this tuple. Changing it to a scalar breaks ticker queries (v1.0.1 lesson).
2. **Never change `Protocolo_Entrega` as dedup key** — It's the unique CVM filing protocol number. Changing it breaks idempotent re-syncs.
3. **Never create `.bak` files** — Forbidden by project rules.
4. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
5. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always unpack the `(cnpj, cd_cvm)` tuple** when calling `_resolve_via_bridge()`.
2. **Always use `cnpj_digits()` for CNPJ comparisons** — IPE eventos table may have formatted CNPJs.
3. **Always use `UNIQUE(protocolo)` for dedup** — Prevents duplicate event rows on re-sync.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

- **v1.0.1 lesson:** `query()` called `_resolve_via_bridge()` expecting a string, but bridge v1.2 changed it to return a tuple. Caused `sqlite3.ProgrammingError: type 'tuple' is not supported`. Fix: unpack the tuple.
