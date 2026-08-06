<- Back to [MACRO](../MACRO.md)

# 🗺️ Macro Roadmap

## P2 (Next)

1. **Wire "sgs" into `skills/_base._trigger_sync.sync_map`** — currently the sync guard for `required_sources=["sgs"]` records an error in `result["_sync"]["errors"]` and proceeds (because `sync_map` only knows CVM/B3 sources). Add an entry:
   ```python
   "sgs": ("data_sources.bcb.sgs.sync_engine", "sync_all",
           lambda: {"force": True, "trace_id": trace_id}),
   ```
   This makes the sync guard actually trigger `sync_all` when SGS is stale (>24h or missing).

2. **Real-returns mode** — Fisher equation: real rate = (1 + nominal) / (1 + inflation) - 1. Uses Selic (11) + IPCA (433), both already in the catalog. New mode `real_returns` in `modes/real_returns.py`.

3. **Yield curve mode** — Plot the term structure of interest rates using DI futures (requires adding DI series to the catalog). New mode `yield_curve`.

4. **Inflation expectations mode** — BCB publishes market expectations (Focus survey) via a separate API endpoint. Could add a new sub-domain `data_sources/bcb/focus/` with expected IPCA / Selic / GDP growth.

---

## P3 (Later)

1. **Historical PIB chart** — The Atividade tab currently shows the last 8 quarters. Add a longer historical chart (5Y / 10Y toggle) using the `price_range_selector` pattern from CVM financials.

2. **Cross-currency dashboard** — Add EUR/BRL, GBP/BRL, JPY/BRL to the Cambio tab. BCB SGS has these series (codes 1.eur, 1.gbp, etc. — need to verify).

3. **Credit market indicators** — Add credit volume + default rate series (BCB SGS codes in the 20000+ range). New category "Credito".

---

## Done (v1.0)

- ✅ 12 series in catalog (TR 226 restored from v1).
- ✅ v1 sync_state schema (series_code / last_date / synced_at / row_count) with DROP TABLE migration.
- ✅ Tab field `name` (was `label`).
- ✅ Top-level KPIs (was per-tab).
- ✅ CDI KPI daily `% a.d.` (was annualized).
- ✅ Chart.js `chart_data` config (was separate labels/values arrays).
- ✅ Table rows as list of lists (was list of dicts).
- ✅ helpers.py syntax fixed (`monthly_values[max(0, i - 11): i + 1]`).
- ✅ conftest.py with real temp SQLite DB fixture.
- ✅ Standalone `_registry.py` fallback (no skills/_base dependency for testing).

---

*Last updated: 2026-07-24 (v1.0).*
