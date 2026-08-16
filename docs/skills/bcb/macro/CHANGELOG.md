<- Back to [MACRO](../MACRO.md)

# 📋 Macro Changelog

## v1.3 — 2026-08-15

**Bug fixes: Resumo table units + inflation row count + Salário label + catalog descriptions.**

### Required Summary

- **USD/BRL mensal chart fixed** — series 24369 was NOT USD/BRL (returns values like 7.6 when the exchange rate was ~4.15). Removed 24369 from the catalog + now computes monthly averages directly from the daily series (1) by grouping daily observations by YYYY-MM and averaging. The monthly chart + table now show correct exchange rate values.
- **USD/BRL charts inverted to show USD/BRL (1/rate)** — charts now show USD/BRL (1/ptax = ~0.19, "dollars per real") instead of BRL/USD (5.x, "reais per dollar"). KPI cards stay as BRL/USD (Brazilian convention). Both daily + monthly charts now have the range selector buttons (Tudo/10A/5A/1A/6M/3M/1M) — added `price_full_datasets` to `build_chart_section` (was missing — buttons rendered but didn't work). Monthly chart now fetches 2 years (730 days) of daily data + shows 24 months via range selector.
- **Resumo table units fixed** — `query_engine.last_value()` now returns `unit` + `name` from `SERIES_CATALOG`. The Resumo table was showing raw Python floats (e.g. `0.05166` instead of `0.051660%`) + empty "Unidade" column because `last_value()` didn't return a `unit` field. Now `format_value(lv["value"], lv["unit"])` formats correctly.
- **Inflation mode row count fixed** — `inflation.py` was passing `days=months*31` to `query_series()`, but `days` is actually a row-count LIMIT (not calendar days). For months=24, this returned up to 744 monthly rows (decades of data). Fixed to pass `days=months` directly — returns the most recent N monthly observations as intended.
- **Salário mínimo label fixed** — changed from "(anual)" to "(mensal)" in the Atividade tab. Series 1619 is monthly in the catalog; the label was misleading.
- **Catalog descriptions fixed** — removed misleading "(anualizada)" from series 11 (Selic) + 12 (CDI) descriptions. The stored value is the daily rate (`% a.d.`, ~0.05%); the description claimed "anualizada" which was confusing.

## v1.2 — 2026-08-13

**Docs sync — sgs sync_map wiring documented.**

### Required Summary

- **sgs sync_map entry documented** — the `sgs` entry in `skills/_base._trigger_sync.sync_map` was added in an earlier commit (the `historical` skill's `required_sources=["sgs"]` now actually triggers `sync_all(force=True)` when SGS is stale), but the fix shipped without a CHANGELOG entry. v1.2 documents the wiring + updates the ROADMAP (moves "Wire sgs into sync_map" from P2 to Done). Also fixed a stale comment in `_base.py` that said `sync_all(force=False)` (the actual lambda passes `force=True`).

## v1.1 — 2026-08-06

**Finetune: range selector + default window + CDI mock fix.**

### Required Summary

- **Default windows expanded** — `days=365` (was 30), `months=24` (was 12) for meaningful trends.
- **`price_range_selector`** on all chart sections — adds Tudo/5A/1A/1M time-range buttons. `price_full_labels` + `price_full_data` carry the full series; the JS frontend slices client-side.
- **CDI KPI mock fix** — `_batch_last_values()` (batched SQL) bypassed the test mock for `last_value`, causing `test_dashboard_cdi_kpi_is_daily` to fail when a real BCB DB existed. Replaced with direct `last_value()` calls (mockable, still efficient on local SQLite).
- **Resumo as TABLE** (was text section) — renders properly in the dashboard template.

## v1.0 — 2026-07-24

**Initial dashboard release.**

### Required Summary

- **Tab field `name`** (was `label`) — the `dashboard.html` template reads `tab.name`, not `tab.label`.
- **Top-level `kpis`** (was per-tab `kpis`) — the template renders KPIs in a universal header above tabs.
- **CDI KPI daily** (was annualized) — per user request: "on top boxes, display CDI not anualizado, but current for the day". Selic KPI stays annualized.
- **Chart.js `chart_data`** (was separate `labels` + `values` arrays) — chart sections now emit a proper Chart.js config dict so the template can render via `new Chart(canvas, config)`.
- **Table rows as list of lists** (was list of dicts) — `[["2024-01-02", "0.001234"], ...]` so the template's `data_table` macro can iterate cells directly.
- **helpers.py syntax fixed** — `monthly_values[max(0, i - 11): i + 1]` (v1 had `monthly_valuesax(0, i - 11): i + 1]`).
- **5 descriptive PT-BR tab names** — Resumo, Juros, Inflacao, Cambio, Atividade (per user request: "on side bar - menu, just generic names").
- **TR (226) added to rates mode** — was dropped in the initial draft.

### Dashboard Tabs (5)

| Tab | Name | Group | Content |
|-----|------|-------|---------|
| 1 | Resumo | Resumo | Text overview. |
| 2 | Juros | Indicadores | rates mode sections (5 series). |
| 3 | Inflacao | Indicadores | inflation mode sections (2 series). |
| 4 | Cambio | Indicadores | fx mode sections (2 series). |
| 5 | Atividade | Indicadores | PIB + Salario minimo (chart + table). |

### KPI Cards (4, top-level)

| KPI | Series | Unit | fix |
|-----|--------|------|--------|
| Selic (anualizada) | 11 | % a.a. | (unchanged from the initial draft) |
| CDI (diaria) | 12 | % a.d. | **daily, NOT annualized** |
| IPCA (mes) | 433 | % | (unchanged) |
| USD/BRL (ptax) | 1 | R$ | (unchanged) |

### Modes (4)

dashboard, rates, inflation, fx.

---

*Last updated: 2026-08-13 (v1.2).*
