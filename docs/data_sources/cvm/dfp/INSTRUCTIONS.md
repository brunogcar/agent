<- Back to [DFP Overview](../DFP.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never change the `meses` computation** — It mirrors rapinav2's `monthsDiff()` (inclusive formula). Changing it breaks period filtering for all downstream consumers.
2. **Never store DMPL rows** — DMPL is a 2D statement (COLUNA_DF) that conflicts on PK. Intentionally excluded (v1.0.1).
3. **Never skip the ORDEM_EXERC filter** — Keeps ÚLTIMO only (+ PENÚLTIMO for 2009 transition). Without it, duplicate periods appear.
4. **Never skip VERSAO dedup** — Keeps the highest version per (cnpj, ano). Without it, restated filings create duplicates.
5. **Never store CNPJ raw (formatted)** — Always use `cnpj_digits()` at ingest (v1.2.1 fix). The resolver uses `REPLACE()` as a safety net, but clean ingest is preferred.
6. **Never create `.bak` files** — Forbidden by project rules.
7. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
8. **Never print to stdout** — MCP stdio corruption. Use `core.tracer` or stderr.

### ALWAYS DO

1. **Always use `cnpj_digits()` for CNPJ at ingest** — v1.2.1 fix. The CSV has formatted CNPJs.
2. **Always use `parse_escala()` for escala values** — DFP stores escala as Portuguese words ("MIL", "MILHOES", "UNIDADE"), not numbers.
3. **Always filter `meses=12` for annual queries** — DFP also has meses=15 (rare transition). Don't assume all rows are annual.
4. **Always multiply `valor * escala` for BRL amounts** — `valor` is in units of `escala` (usually thousands).
5. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

*(Fill this section with relevant info from edits and refactors. Add lessons learned as they are discovered.)*

- **v1.2.1 lesson:** DFP sync stored CNPJ raw ("33.000.167/0001-01") from the CSV. The bridge resolver uses `REPLACE()` to normalize on-the-fly, but this is a safety net — sync should use `cnpj_digits()` at ingest.
