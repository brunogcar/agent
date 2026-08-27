<- Back to [INVESTSITE Overview](../INVESTSITE.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v2.1** | 2026-08-27 | **Session auth (Cloudflare Turnstile).** investsite.com.br now requires login (Cloudflare Turnstile CAPTCHA on login.php). All data pages redirect to login (302) without a SESSION_ID cookie. Updated `fetcher.py` to: (1) send SESSION_ID cookie with every request, (2) read credentials from `cfg` (via `core.config` — ensures `.env` is loaded), (3) auto-detect 302 → login redirect and raise a clear error, (4) automated browser login path via Playwright (if `INVESTSITE_EMAIL` + `INVESTSITE_PASSWORD` set — Turnstile auto-solves in real browser context). Also fixed broken imports in `valuation/fetchers.py` + `calculations/engines/shares.py` (`from skills.investsite.investsite import indicators` → `from skills.investsite.modes.indicators import indicators`). Added `INVESTSITE_SESSION_ID`, `INVESTSITE_EMAIL`, `INVESTSITE_PASSWORD` to `core/config_backend/services.py` + `.env.example`. |
| **v2.0** | 2026-08-02 | **Dashboard overhaul mirroring financials/valuation pattern.** Complete rewrite of dashboard mode + report.py. 12 tabs in 4 sidebar groups: Resumo (Overview with company header + split tables + charts), Indicadores (Preços Relativos, Retornos e Margens, Balanço, Experimental — each with tables + bar charts + tooltips), Demonstrações (DRE TTM+Quarterly+full statement, DFC TTM+Quarterly+full, BPA, BPP, DVA), Corporativo (Eventos, Quantidade de Ações). Company header from dados_basicos. Tooltips on all table metric names (dict cells with ⓘ icon). Chart titles + descriptions on all charts. Freshness footer ("Dados de: investsite.com.br"). Adapter preserves group field + passes company_header + freshness_footer. 26 tests pass. |
| **v1.2** | 2026-07-31 | **Dashboard reorg.** Added indicator bar chart (P/L, P/VPA, EV/EBITDA comparison) to Key Indicators tab. Added `build_indicator_chart()` to report.py. ROADMAP.md created. 7 tests (was 6). |
| **v1.3** | 2026-07-30 | **skills/_base/ extraction.** _registry.py + __init__.py now delegate to the shared `skills/_base/` module. |
| v1.1 | 2026-07-29 | **Modular split + dashboard mode.** Split the monolithic `investsite.py` (185 lines) into the canonical modular structure: `_registry.py` (ModeSpec + register_mode + auto-discovery) + `modes/{indicators,statements,events,listing,summary,dashboard}.py` (6 mode files) + `report.py` (NEW dashboard composition helpers). `fetcher.py` + `parsers.py` KEPT as separate modules — only `investsite.py` was split. Added a new `dashboard` mode (the 6th investsite mode) that composes `indicators()` + `events()` into a 3-tab payload (Overview/Key Indicators/Latest Events) with 5 top-level KPI cards (P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield). Added the first investsite report adapter `investsite_dashboard` (top-level flat domain — no pre-existing investsite_* adapters). `__init__.py` rewritten with auto-discovery (preserves `"domain"` not `"sub_domain"` + `route(sub_domain="", mode="", **kwargs)` signature — sub_domain accepted but ignored). 33 tests (18 original + 15 NEW TestDashboardMode) + 10 NEW TestInvestsiteDashboardAdapter. |
| v1.0 | 2026-07-24 | **Initial implementation.** 5 modes: indicators (default, 10 tables), statements (BPA/BPP/DRE/DFC/DVA/shares with % total), events (IPE by category with CVM PDF links), summary, listing. Live HTTP fetching with httpx + browser headers. In-memory cache (1h TTL). Rate-limited (0.5s). 18 tests. |

---

## 🔄 In Progress / Next Up

- **Statement charts (I3)** — Add bar/doughnut charts from statements data.
- **Sidebar optimization (I5)** — Smaller sidebar items for 12+ tabs.
- **More tooltips (I6)** — Tooltips on DFC, BPA, BPP, DVA, shares account rows.
- **Browser charts (I4)** — Playwright extraction of amCharts data (Desempenho, DuPont, etc.).
- **b3-api improvement** — Port the "goldmine" indicators from investsite to local DFP/ITR computation.
- **Batch tickers** — Fetch indicators for multiple tickers in one call (for screening).
- **Error resilience** — If investsite changes HTML structure, parsers should degrade gracefully.

---

## 🚫 Deferred / Out of Scope

- **Local DB caching** — User prefers live fetching. If caching becomes needed, add a `data_sources/investsite/` that syncs to SQLite with 24h TTL.
- **Historical price data** — Full price history would need chart data (browser tool).
- **Authentication** — [v2.1] investsite now requires login (Cloudflare Turnstile). Session auth via INVESTSITE_SESSION_ID env var (manual) or INVESTSITE_EMAIL + INVESTSITE_PASSWORD (automated browser login via Playwright).

---

*Last updated: 2026-08-27 (v2.1 — session auth). See [CHANGELOG.md](CHANGELOG.md) for version history.
