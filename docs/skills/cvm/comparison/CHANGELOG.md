<- Back to [COMPARISON Overview](../COMPARISON.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-07-25 | **Initial implementation.** 2 modes: side_by_side (3 sections — valuation, financials, dividends), summary (single quick-compare table). Orchestrates financials.summary + valuation.ratios + dividends.summary per ticker. Best-effort per ticker — one source failing doesn't break the comparison. 2 report adapters (comparison_side_by_side, comparison_summary). 22 skill tests + 6 adapter tests. Read-only — no own database. |

---

## 🔄 In Progress / Next Up

- **Growth mode** — QoQ/YoY % change for revenue, EBITDA, net income across tickers. Trivial from financials quarterly_trend.
- **Sector tagging** — auto-tag tickers by B3 sector (from brapi or CAD) so the LLM can group comparisons.
- **Historical comparison** — compare tickers at a past date (e.g. "PETR4 vs VALE3 as of 2022-12-31"). Needs COTAHIST historical prices + point-in-time financials.
- **Valuation-only mode** — `valuation_only` mode that skips financials/dividends (faster for quick P/L screens). Additive — won't change existing modes.
- **Custom column selection** — `columns` param to let the LLM pick which metrics to include (e.g. only P/L + ROE + Div Yield).

---

## 🚫 Deferred / Out of Scope

- **Cross-sector benchmarks** — aggregate financials across a whole sector for median P/L, ROE, etc. Separate skill (e.g. `skills/cvm/screener`).
- **Charts** — radar/spider chart comparing tickers across normalized metrics. Belongs in report tool as a chart adapter (v1.3 roadmap).
- **Real-time price delta** — comparison uses 15-min delayed brapi prices. Real-time needs paid B3 feeds.

---

*Last updated: 2026-07-25 (v1.0).*
