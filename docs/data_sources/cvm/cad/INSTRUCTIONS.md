<- Back to [CAD Overview](../CAD.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never implement partial sync** — CAD is full-replace only. The CSV is a complete snapshot (~2677 companies, ~1.5MB). Incremental sync would miss deletions/status changes.
2. **Never skip CNPJ normalization** — Always use `cnpj_digits()` when storing or querying CNPJ. The CSV has formatted CNPJs ("33.000.167/0001-01").
3. **Never change the 46-column schema** — `ALL_COLS` maps the CSV exactly. Adding/removing columns breaks the dynamic INSERT.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `cnpj_digits()` for CNPJ comparisons** — The DB may have formatted CNPJs; normalize before comparing.
2. **Always use `DEFAULT_COLS` (24) by default** — `full=True` returns all 46 columns (noisy). Only use `full` when explicitly needed.
3. **Always update `sync_state` after sync** — Records the sync timestamp for freshness checks.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*
