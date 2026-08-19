<- Back to [MACRO](../MACRO.md)

# 🗺️ Macro Roadmap

## P2 (Next)

1. **Focus expectations mode** — BCB publishes market expectations (Focus survey) via a separate Olinda OData API endpoint. Could add a new sub-domain `data_sources/bcb/focus/` with expected IPCA / Selic / GDP growth, then a new `expectations` mode + 7th "Expectativas Focus" tab.

2. ~~**Yield curve mode**~~ — **DONE in v1.5 (Option B — Focus).** Ships a Focus-based yield curve: queries `data_sources.bcb.focus.query_engine.expectations(indicador="Selic", frequency="annual")`, groups by `data_referencia` (year), keeps the latest median per year, and charts the expected Selic path with a min/max band. New `yield_curve` mode + 8th "Curva de Juros" dashboard tab. **Option A (BMF DI futures) deferred** — B3 does not publish BMF historical data at a public URL like COTAHIST. Needs API portal investigation.

3. **Credit market indicators** — Add credit volume + default rate series (BCB SGS codes in the 20000+ range). New category "Credito".

---

## P3 (Later)

1. **Historical PIB chart** — The Atividade tab currently shows the last 8 quarters. Add a longer historical chart (5Y / 10Y toggle) using the `price_range_selector` pattern from CVM financials.

2. **Cross-currency dashboard** — Add EUR/BRL, GBP/BRL, JPY/BRL to the Cambio tab. BCB SGS has these series (codes 1.eur, 1.gbp, etc. — need to verify).

---

## Done

- ✅ **Yield curve mode (v1.5) — Option B (Focus)** — New `yield_curve` mode in `modes/yield_curve.py`. Builds an expectations-based yield curve from BCB Focus Selic annual expectations: queries ALL Selic annual observations, groups by `data_referencia` (year, e.g. "2026"), keeps the latest median per year, charts DataReferencia (x) vs Mediana (y) with min/max dashed bands (uncertainty range). 3 KPIs: Selic atual (SGS series 432 = "Meta Selic Copom"), Selic esperada próximo ano (Focus median for current_year + 1), Selic longo prazo (Focus median for current_year + 5, or farthest year available). Added 8th "Curva de Juros" tab to the dashboard (group: Analise). `_SEC_TOTAL` bumped 7 → 8. **Option A (BMF DI futures) deferred** — B3 does not publish BMF historical data at a public URL like COTAHIST. Needs API portal investigation.
- ✅ **Real-returns mode (v1.4)** — Fisher equation: `real = (1 + nominal) / (1 + inflation) - 1`. Nominal = Selic annualized (series 11). Inflation = IPCA 12m acumulado (series 433). New mode `real_returns` in `modes/real_returns.py`. Added 6th "Retorno Real" tab to the dashboard (group: Analise).
- ✅ **sgs sync_map wiring (v1.2 docs)** — the `sgs` entry in `skills/_base._trigger_sync.sync_map` was added in an earlier commit: `("data_sources.bcb.sgs.sync_engine", "sync_all", lambda: {"force": True})`. The `historical` skill's `required_sources=["sgs"]` now actually triggers `sync_all(force=True)` when SGS is stale (>24h or missing) instead of recording an error + proceeding. v1.2 documents the wiring + fixes a stale comment drift.
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

*Last updated: 2026-09-05 (v1.5 — yield_curve shipped, Option B Focus).*
