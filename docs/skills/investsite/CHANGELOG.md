<- Back to [INVESTSITE Overview](../INVESTSITE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.1 | 2026-07-29 | **Modular split + dashboard mode.** Split the monolithic `investsite.py` (185 lines) into the canonical modular structure: `_registry.py` (ModeSpec + register_mode + auto-discovery) + `modes/{indicators,statements,events,listing,summary,dashboard}.py` (6 mode files) + `report.py` (NEW dashboard composition helpers). `fetcher.py` + `parsers.py` KEPT as separate modules — only `investsite.py` was split. Added a new `dashboard` mode (the 6th investsite mode) that composes `indicators()` + `events()` into a 3-tab payload (Overview/Key Indicators/Latest Events) with 5 top-level KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield). Added the first investsite report adapter `investsite_dashboard` (top-level flat domain — no pre-existing investsite_* adapters). `__init__.py` rewritten with auto-discovery (preserves `"domain"` not `"sub_domain"` + `route(sub_domain="", mode="", **kwargs)` signature — sub_domain accepted but ignored). 33 tests (18 original + 15 NEW TestDashboardMode) + 10 NEW TestInvestsiteDashboardAdapter. |
| v1.0 | 2026-07-24 | **Initial implementation.** 5 modes: indicators (default, 10 tables), statements (BPA/BPP/DRE/DFC/DVA/shares with % total), events (IPE by category with CVM PDF links), summary, listing. Live HTTP fetching with httpx + browser headers. In-memory cache (1h TTL). Rate-limited (0.5s). 18 tests. |

---

## 🔄 In Progress / Next Up

- **Charts (browser tool)** — investsite uses amCharts with dynamically-loaded data. Pages: Desempenho Operacional, Análise DuPont, Dividend Yield, Aluguel de Ações. Need Playwright (browser tool) to extract — investigate viability in a future spike.
- **b3-api improvement** — Port the "goldmine" indicators (P/L, P/VPA, P/FCO, EV, Dividend Yield, ROIC, Dívida Líq/EBITDA, CAPEX, FCF) from investsite to `data_sources/b3/api` or a new skill, so they're computed from our local DFP/ITR data instead of scraped. See ARCHITECTURE.md for the full indicator list.
- **Batch tickers** — Fetch indicators for multiple tickers in one call (for screening). Currently single-ticker only.
- **Error resilience** — If investsite changes HTML structure, parsers should degrade gracefully (return partial data, not crash).

---

## 🚫 Deferred / Out of Scope

- **Local DB caching** — User prefers live fetching. If caching becomes needed, add a `data_sources/investsite/` that syncs to SQLite with 24h TTL.
- **Historical price data** — Full price history would need chart data (browser tool).
- **Authentication** — investsite is free, no login needed.

---

*Last updated: 2026-07-29 (v1.1).*
