<- Back to [CGVN Overview](../CGVN.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never use UTF-8 decoding for CVM CSVs** — CVM uses latin-1 encoding. UTF-8 will crash on Portuguese accented characters.
2. **Never use exact filename matching** — CVM adds year suffixes to CSV filenames. Match by prefix, not exact name.
3. **Never DELETE all rows on re-sync** — Use year-based DELETE (WHERE Data_Referencia starts with year) to preserve other years.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only.
6. **Never print to stdout** — MCP stdio corruption.

### ALWAYS DO

1. **Always use batch INSERT (5K)** — Individual INSERTs are 10x slower for large CVM datasets.
2. **Always convert numeric fields** — CVM uses comma as decimal separator. Replace comma with dot before float conversion.
3. **Always record sync_state** — Track year + rows_synced for incremental sync support.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors.)*

---

*Last updated: 2026-07-25 (v1.0).*
