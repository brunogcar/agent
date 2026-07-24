<- Back to [VALUATION Overview](../VALUATION.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never fetch price from the web** — Use b3 trades.db (local). The investsite skill is for web data; this skill uses local databases only.
2. **Never compute ratios without checking for None** — Use `_safe_div()` for all divisions. Returns None on zero/None denominator.
3. **Never change the ratio formulas** — P/L = price/EPS, P/VPA = price/VPA, EV = Market Cap + Debt - Cash. These are standard definitions.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
6. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `core/br_validator`** for BRL/date/ticker parsing — `validate_ticker()`, `parse_escala()`, `parse_brl()`. Financial skills MUST use br_validator for consistency.
2. **Always include underlying values in the response** — price, EPS, VPA, shares, etc. so callers can verify the ratio computation.
3. **Always return data source status** — If b3 trades.db or fre.db is missing, return `None` for affected ratios + a note explaining what's missing.
4. **Always use `parse_escala()` for DFP escala values** — DFP stores escala as Portuguese words ("MIL", "MILHOES").
5. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*
