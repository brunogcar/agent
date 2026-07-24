<- Back to [FRE Overview](../FRE.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never change `_resolve_via_bridge()` tuple unpacking** — It returns `(cnpj, cd_cvm)`. The `_resolve_fre_company` function unpacks this tuple. Changing it to a scalar breaks ticker queries (v1.0.1 lesson).
2. **Never change `ID_DOC` as primary key** — It's a globally unique CVM filing ID. Changing it breaks dedup across years.
3. **Never import all 50+ CSVs** — Only 5 tables are imported (the analytically useful ones). The rest are text-heavy governance sections.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always unpack the `(cnpj, cd_cvm)` tuple** when calling `_resolve_via_bridge()`.
2. **Always use `cnpj_digits()` for CNPJ comparisons** — FRE documentos table may have formatted CNPJs.
3. **Always use `UNIQUE(id_documento, cpf_cnpj_acionista)` for posicao_acionaria dedup** — Prevents duplicate shareholder rows.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

- **v1.0.1 lesson:** `_resolve_fre_company` called `_resolve_via_bridge()` expecting a string, but bridge v1.2 changed it to return a tuple. Caused `sqlite3.ProgrammingError: type 'tuple' is not supported`. Fix: unpack the tuple.
