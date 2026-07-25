<- Back to [SCREENER Overview](../SCREENER.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never query the database directly from screener** — screener orchestrates CAD + bridge + valuation. If you need a new metric, add it to the underlying skill, then reference it here. No SQL in screener.py.
2. **Never fail the whole screener on a per-company error** — companies without a ticker or with failed valuation are skipped. The `errors` list captures what was skipped.
3. **Never change the sort order** — peers are sorted by P/L cheapest-first. This is intentional for value investors. None P/L goes last.
4. **Never compute medians with None values** — use `statistics.median()` over non-None values only. If a metric is None for all peers, median is None.
5. **Never register adapters outside `tools/report_ops/adapters/`** — `adapters/__init__.py` imports the screener module to trigger `@register_adapter`.

## ✅ ALWAYS DO

6. **Always reuse `sector()` from `compare()`** — compare mode calls sector() to get peers + medians, then builds the comparison. Don't duplicate the peer-fetching logic.
7. **Always uppercase tickers** — `ticker = company.strip().upper()`.
8. **Always include `vs_sector` label** — "cheap"/"expensive" for P/L, P/VPA, EV/EBITDA; "above"/"below" for ROE, Div Yield. This is what the LLM reads to judge valuation.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet.)*

---

*Last updated: 2026-07-25 (v1.0).*
