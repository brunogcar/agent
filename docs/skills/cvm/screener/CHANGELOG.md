<- Back to [SCREENER Overview](../SCREENER.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.2 | 2026-07-27 | **Calculations integration.** (1) `_roe_from_ratios()` simplified — now reads `ratios["roe"]` directly (since Phase 2B, valuation.ratios() returns roe computed by calculations.metrics.roe_at). Removed the lucro_liquido/patrimonio_liquido fallback (those keys aren't reliably populated in valuation's output — they live in financials.summary). (2) `sector()` peer dict extended with `roa`, `margem_liquida`, `divida_pl` from valuation.ratios. (3) `compare()` fallback path extended with the same 3 metrics. (4) `_compute_medians()` extended with the 3 new metrics (medians dict is additive — all v1.1 keys still present). (5) `_build_comparison()` extended with the 3 new metrics — roa + margem_liquida classified as "above"/"below" (higher = better), divida_pl classified as "cheap"/"expensive" (lower leverage = cheaper risk profile). Single test file (174 lines, 4 classes) split into `conftest.py` + 4 per-mode files (validation / sector / compare / route) following the Phase 2C pattern. 13 tests (was 12 — added 1 new test asserting v1.2 metrics populate in peers). All existing keys + labels preserved. |
| v1.1 | 2026-07-25 | **Financials enrichment.** screener.sector now calls financials.annual(periods=2) per peer to add Receita, EBITDA, Lucro Liquido, Marg. EBITDA, Marg. Liquida, Payout, and Cresc. Receita (YoY). Best-effort — financials failures don't skip the peer. Adapter enriched with 7 new columns. |
| v1.0 | 2026-07-25 | **Initial implementation.** 2 modes: sector (list peers + medians), compare (is ticker cheap/expensive vs sector). Orchestrates CAD + bridge + valuation. Best-effort — skips companies without ticker or failed valuation. Peers sorted by P/L cheapest-first. 1 report adapter (screener_sector). 15 skill tests. |

---

## 🔄 In Progress / Next Up

- **Custom metric selection** — let the LLM specify which metrics to include (e.g. only P/L + ROE).
- **Historical comparison** — compare a ticker's current P/L vs its own historical P/L range (needs COTAHIST + historical financials).
- **Adapter enrichment** — the `screener_sector` adapter (`tools/report_ops/adapters/screener.py`) currently shows the v1.1 peer columns. It can be extended with `roa`, `margem_liquida`, `divida_pl` columns + median KPIs in a future revision. The skill already returns the data — only the adapter needs updating.

---

## 🚫 Deferred / Out of Scope

- **Real-time price** — uses 15-min delayed brapi. Real-time needs paid B3 feeds.
- **Cross-sector comparison** — comparing a ticker against multiple sectors. Each sector has different economics; cross-sector comparison is usually misleading.
- **Direct calculations calls** — screener could in principle call calculations metrics directly (e.g. `roic_at` for a per-peer ROIC column), but the current design uses valuation.ratios() as the single funnel. This avoids duplicate DB queries (valuation already calls the engines) and keeps the orchestration boundary clean. Deferred until a metric is needed that valuation doesn't expose.

---

*Last updated: 2026-07-27 (v1.2).*
