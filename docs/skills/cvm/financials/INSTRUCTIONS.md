<- Back to [FINANCIALS Overview](../FINANCIALS.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never add sync logic to a skill** — Skills are read-only. They call data_source query engines. Sync belongs in `data_sources/`.
2. **Never use `float(escala)` directly** — DFP stores escala as Portuguese words ("MIL", "MILHOES"). Always use `parse_escala()` from `_db.py`.
3. **Never return cumulative values as standalone** — ITR values are cumulative. Flow items (DRE/DFC/DVA) must be subtracted to get standalone quarters. Snapshot items (BPA/BPP) use period-end value directly.
4. **Never change the EBITDA formula** — `EBITDA = EBIT (DRE 3.05) + D&A (DFC 6.01.01.02)`. The D&A comes from the cash flow statement, not the DRE.
5. **Never change the Q4 derivation** — `Q4 = DFP annual (meses=12) − ITR Q3 cumulative (meses=9)`. This requires both DFP + ITR to be synced.
6. **Never create `.bak` files** — Forbidden by project rules.
7. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
8. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `parse_escala()` for escala values** — `float("MIL")` crashes.
2. **Always make summary sections best-effort** — If one data source is missing, the summary should still return what's available.
3. **Always annualize ROA/ROE for quarterly** — `lucro_liquido * 4 / ativo_total`. Document that TTM is on the roadmap.
4. **Always return `period_type` in the result** — So callers know if it's "annual" or "quarterly".
5. **Always sort periods newest-first** — Consistent with other skills.
6. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*
