<- Back to [COTAHIST Overview](../COTAHIST.md)

# 🛡️ AI Instructions

### NEVER DO

1. **Never sync all years without BDI filter** — Without BDI_FILTER={02,12,14,96}, the DB grows to ~5.7GB (options, bonds, warrants). Always filter at sync time.
2. **Never query without market_type filter** — A ticker trades on both lote padrão (10) and fracionário (12), producing duplicate rows. Default market_type=10 avoids this.
3. **Never load the full TXT into memory** — 765MB per year. Use line-by-line streaming parser.
4. **Never create `.bak` files** — Forbidden by project rules.
5. **Never rewrite entire files** — Surgical edits only.
6. **Never print to stdout** — MCP stdio corruption.

### ALWAYS DO

1. **Always use batch INSERT (50K)** — Individual INSERTs are 10x slower. Batch transactions reduce SQLite write overhead.
2. **Always divide numeric columns by 100** — B3 stores prices without decimal points (3850 = R$38.50). NUMERIC_COLS handles this.
3. **Always record sync_state** — Track year, rows_added, duration_s for monitoring.
4. **Always run `compileall` before `pytest`** — Catches syntax errors early.

---

### Anti-patterns & Lessons Learned

- **v1.0.1 lesson:** BDI filter missing in initial implementation — DB was 5.7GB with 852K tickers (mostly options). Fixed by filtering at sync time → 1-2GB, 4,959 tickers.
- **v1.0.1 lesson:** Duplicate rows — ticker trades on both lote padrão + fracionário. Fixed by defaulting query to market_type=10.

---

*Last updated: 2026-07-25 (v1.0).*
