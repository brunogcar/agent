<- Back to [MACRO](../MACRO.md)

# 📋 Macro Changelog

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
