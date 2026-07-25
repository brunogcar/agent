<- Back to [COMPARISON Overview](../COMPARISON.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never query the database directly from comparison** — comparison orchestrates the 3 existing skills. If you need a new metric, add it to the underlying skill (financials/valuation/dividends), then reference it in the column lists here. No SQL in comparison.py.
2. **Never fail the whole comparison on a per-ticker error** — `_fetch_all()` wraps each skill call in try/except. A ticker failing one source gets `None` cells, not a raised exception. The `errors` list captures what failed.
3. **Never change a `dict_key` without checking the source skill** — the `dict_key` in `_VALUATION_COLS` / `_FINANCIALS_COLS` / `_DIVIDENDS_COLS` must match the key the underlying skill emits. If you rename a key in valuation.ratios, update `_VALUATION_COLS` in the same commit.
4. **Never add a column with a different unit to an existing section** — each section is unit-homogeneous (all BRL, all %, all multiples). A mixed-unit section breaks per-column format specs. Add a new section instead.
5. **Never collide dict_keys across sources in summary mode** — `summary()` merges valuation + financials + dividends dicts. If two sources emit the same key (e.g. `dividend_yield`), the later one overwrites. `dividend_yield` comes from valuation, not dividends — don't add it to `_DIVIDENDS_COLS`.
6. **Never register adapters outside `tools/report_ops/adapters/`** — `adapters/__init__.py` imports the comparison module to trigger `@register_adapter`. New adapter files must be added there.

## ✅ ALWAYS DO

7. **Always update both skill tests and adapter tests** when changing column lists — `tests/skills/cvm/test_comparison.py` checks column names + values; `tests/tools/report/test_report_adapters.py` checks adapter pass-through.
8. **Always keep `errors` list populated** — if a per-ticker skill fails, append to `entry["error"]` and let it flow to `r["errors"]`. The caller needs to know data is partial.
9. **Always uppercase tickers** — `tickers = [t.strip().upper() for t in tickers]` at the start of each mode. Underlying skills expect uppercase.
10. **Always reuse `_build_section()`** for new sections — it handles the columns/rows/formats construction. Don't hand-build section dicts.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes.)*

---

*Last updated: 2026-07-25 (v1.0).*
