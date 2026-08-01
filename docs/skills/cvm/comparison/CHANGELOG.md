<- Back to [COMPARISON Overview](../COMPARISON.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.2** | 2026-08-02 | **Dashboard reorg (charts + print output).** Added 2 Chart.js chart builders + 1 ratio_grid builder to `report.py`: `build_peer_comparison_chart(company, peers, metric_name)` (vertical bar chart comparing the target ticker vs peers on a key metric — target highlighted in purple, valuation multiples in teal, profitability in orange, leverage in red; supports 8 metrics via `_PEER_METRIC_DEFS`) + `build_peer_ratio_grid(peers)` (ratio_grid section grouping 9 peer metrics into 3 categories: Valuation, Profitability, Leverage). Both return their section dict or None when no peer data. Dashboard mode now appends the peer comparison chart (default metric=p_l) to the Valuation tab + adds a new 6th "Ratio Grid" tab when peer_ratio_grid returns data (skipped gracefully when all metrics are None — preserves the existing 5-tab degradation when side_by_side fully fails). Added detailed `[comparison]` print output (flush=True) showing the starting message, side_by_side + growth fetch progress, section-building step, + final "Done! N tabs, M KPIs" line. ROADMAP.md created. No sync guard (comparison calls internal skills financials+valuation+dividends which already have their own sync guards). 6 dashboard tests (was 5 — added 1 chart assertion test + updated tab-structure assertion to expect 6 tabs). |
| **v2.0** | 2026-07-30 | **skills/_base.py extraction.** _registry.py + __init__.py now delegate to the shared `skills/_base.py` module (ModeSpec + make_registry + make_route + auto_discover_modes). _registry.py shrank from ~97 lines to ~16 lines; __init__.py shrank from ~88 lines to ~50 lines. No behavior change — same modes, same route() signature, same MANIFEST. Bug fixes to the dispatch infrastructure now only need to be made in ONE place (skills/_base.py) instead of 11. |
| **v1.5** | 2026-07-29 | **File structure split + dashboard mode.** `comparison.py` (518 lines) split into standard modular structure: `_registry.py` + `modes/` (4 files: side_by_side, summary, growth, dashboard) + `fetchers.py` + `helpers.py` + `report.py`. NEW `dashboard` mode — 5-tab dashboard (Overview/Valuation/Financials/Dividends/Growth). Auto-discovery via importlib. |
| **v1.4** | 2026-07-29 | **Surfaced 15 v1.4 valuation metrics in `_VALUATION_COLS`.** The valuation skill's v1.4 work wired 15 new calculations metrics into `ratios()` (EV/Sales, EV/FCF, Cash Ratio, Quick Ratio, OCF Margin, FCF Margin, Working Capital, Cash Flow to Debt, Retention Ratio, Sustainable Growth, Interest Coverage, Inventory Turnover, Receivables Turnover, Fixed Asset Turnover, P/Tangible Book). Comparison picks these up transitively via the existing `entry["valuation"] = r.get("ratios", {})` line in `_fetch_all()` — no new data fetching. Extended `_VALUATION_COLS` with 15 new `(label, dict_key, spec)` entries grouped by family (EV multiples → liquidity → margins → capital structure → growth → coverage → turnover → price/tangible), matching the v1.4 valuation metric families. Format specs: `num` for multiples/turnover/coverage, `pct` for margins/growth/retention, `brl` for working capital. All existing v1.3 columns preserved (ROE (val), ROA (val), Marg. Líq. (val), Dívida/PL, Liquidez Corrente). Now 33 columns in the valuation section (13 base + 5 v1.3 + 15 v1.4). |
| v1.3 | 2026-07-27 | **Calculations integration.** Side_by_side valuation section now surfaces 5 new columns sourced from `valuation.ratios()` (which since Phase 2B delegates to calculations engines): ROE (val), ROA (val), Marg. Líq. (val), Dívida/PL, Liquidez Corrente. No new data fetching — comparison picks these up transitively via the existing `entry["valuation"] = r.get("ratios", {})` line in `_fetch_all()`. Single test file (431 lines, 7 classes) split into `conftest.py` + 5 per-mode files (validation / side_by_side / summary / growth / route) following the Phase 2C pattern. 36 tests (was 31 — added 1 new test asserting v1.3 metrics land in the valuation section). All existing keys + column labels preserved. |
| v1.2.2 | 2026-07-25 | **Growth guard relaxed.** v1.2.1 suppressed |result| >= 500% (magnitude guard) which hid legitimate extreme values. Removed the magnitude guard — extreme same-sign growth is real data the LLM should see. Only sign-change guards remain: prev <= 0 and curr*prev < 0 (opposite signs = meaningless %). SUZB3 lucro QoQ now shows its real extreme value instead of None; KLBN11 (sign change) stays None. |
| v1.2.1 | 2026-07-25 | **Growth sign-change guard fix.** v1.2 caught negative prev and >500% results, but missed profit→loss sign changes (prev positive, curr negative) that produce -400% noise. Fix: add curr*prev<0 check — opposite signs = sign change, % is meaningless. KLBN11 lucro QoQ -395% now correctly suppressed. |
| v1.2 | 2026-07-25 | **Sector tagging + growth guard.** (1) Sector tagging: all 3 modes now return a "sectors" field {ticker: SETOR_ATIV} resolved from CAD via bridge -> CNPJ. (2) Growth sign-change guard: _pct_change returns None when prev <= 0 (sign-change) or |result| >= 500% (tiny-base noise). Fixes the 3612%/-395% noise values seen in v1.1. |
| v1.1 | 2026-07-25 | **Growth mode + Payout fix.** (1) New `growth` mode: QoQ + YoY % change for Receita, EBITDA, Lucro Líquido + TTM Marg. EBITDA + ROE. Calls financials.quarterly(periods=8) per ticker. (2) Payout fix: moved Payout column from _DIVIDENDS_COLS (where it was always null — dividends skill doesn't return it) to _FINANCIALS_COLS (where it lives in latest_annual.ratios.payout). (3) New `comparison_growth` adapter. 8 new skill tests + 2 new adapter tests. |
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
- **Direct calculations calls** — comparison could in principle call calculations metrics directly (e.g. `roic_at` for a per-ticker ROIC column), but the current design uses valuation.ratios() as the single funnel. This avoids duplicate DB queries (valuation already calls the engines) and keeps the orchestration boundary clean. Deferred until a metric is needed that valuation doesn't expose.

---

*Last updated: 2026-08-02 (v1.2 — dashboard reorg).*
