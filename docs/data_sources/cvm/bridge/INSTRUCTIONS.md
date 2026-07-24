<- Back to [BRIDGE Overview](../BRIDGE.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never change `_resolve_via_bridge()` return type** — It returns a `(cnpj, cd_cvm)` tuple (v1.2+). FRE + IPE query engines unpack this tuple. Changing it to a scalar breaks every ticker query.
2. **Never add a `mkt_cap` column** — Market cap lives in instruments.db (may be partial). The bridge is identity-only. Intentionally excluded.
3. **Never remove the ISIN fallback** — It's the backup when the dividends API returns no codeCVM. Without it, those tickers can't be bridged.
4. **Never remove the `auto_sync` parameter from `resolve_company()`** — It defaults to `True` and enables auto-sync-on-demand. Removing it breaks the self-healing behavior.
5. **Never create `.bak` files** — Forbidden by project rules.
6. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
7. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always unpack the `(cnpj, cd_cvm)` tuple** when calling `_resolve_via_bridge()` — see FRE/IPE query engines for the pattern.
2. **Always use `cnpj_digits()` for CNPJ normalization** — CNPJ may be formatted ("33.000.167/0001-01") or normalized ("33000167000101"). `cnpj_digits()` handles both.
3. **Always use `parse_escala()` for escala values** — DFP stores escala as Portuguese words ("MIL", "MILHOES"), not numbers.
4. **Always log sync actions to `sync_log`** — `linked`, `linked_isin`, `no_cvm`, `no_cad`, `error` actions for auditability.
5. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

- **v1.2.1 lesson:** When changing a function's return type (scalar → tuple), grep for ALL callers and update them. The bridge v1.2 changed `_resolve_via_bridge()` to return a tuple but missed FRE + IPE callers — caused `sqlite3.ProgrammingError: type 'tuple' is not supported`.
- **v1.2.1 lesson:** DFP/ITR sync stored CNPJ raw (formatted) from the CSV. The resolver now uses `REPLACE()` to normalize on-the-fly, but future syncs should use `cnpj_digits()` at ingest.
