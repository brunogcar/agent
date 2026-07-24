<- Back to [DIVIDENDS Overview](../DIVIDENDS.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never assume bulk sync** — The dividends API is per-ticker (one HTTP call per ticker). There is no "sync all" endpoint.
2. **Never drop the `isin_code` column** — It's used by the bridge ISIN fallback (ticker → dividends.db ISIN → ISIN ZIP → CNPJ).
3. **Never drop the `code_cvm` column** — It's the primary ticker → cd_cvm link used by the bridge.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always normalize dates (DD/MM/YYYY → YYYY-MM-DD)** — B3 uses PT-BR date format. Store ISO format for consistency.
2. **Always parse rates with comma decimal separator** — B3 uses "0,35" not "0.35". Use `_parse_rate()` which replaces comma with dot.
3. **Always store `company_info` during sync** — The `codeCVM` field is needed by the bridge.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*
