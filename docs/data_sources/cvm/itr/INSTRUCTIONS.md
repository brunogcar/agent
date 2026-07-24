<- Back to [ITR Overview](../ITR.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never change the `meses` computation** — Shared with DFP (rapinav2-compatible). Changing it breaks period filtering.
2. **Never store DMPL rows** — Same as DFP (2D statement, excluded).
3. **Never skip the ORDEM_EXERC filter** — Same as DFP.
4. **Never skip VERSAO dedup** — Same as DFP.
5. **Never store CNPJ raw (formatted)** — Always use `cnpj_digits()` at ingest (v1.2.1 fix).
6. **Never return standalone quarters** — ITR values are CUMULATIVE within the year (Q1=Jan–Mar, Q2=Jan–Jun). Standalone quarter derivation belongs in the skills/ layer, not here.
7. **Never create `.bak` files** — Forbidden by project rules.
8. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
9. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `cnpj_digits()` for CNPJ at ingest** — v1.2.1 fix (same as DFP).
2. **Always use `parse_escala()` for escala values** — Same as DFP.
3. **Always document that ITR values are cumulative** — Callers must not assume standalone quarters.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*
