<- Back to [MACRO](../MACRO.md)

# 📋 Macro Changelog

## v3.0 — 2026-07-24

**Fixes ALL dashboard issues from v2.**

### Required Summary

- **Tab field `name`** (was `label`) — the `dashboard.html` template reads `tab.name`, not `tab.label`.
- **Top-level `kpis`** (was per-tab `kpis`) — the template renders KPIs in a universal header above tabs.
- **CDI KPI daily** (was annualized) — per user request: "on top boxes, display CDI not anualizado, but current for the day". Selic KPI stays annualized.
- **Chart.js `chart_data`** (was separate `labels` + `values` arrays) — chart sections now emit a proper Chart.js config dict so the template can render via `new Chart(canvas, config)`.
- **Table rows as list of lists** (was list of dicts) — `[["2024-01-02", "0.001234"], ...]` so the template's `data_table` macro can iterate cells directly.
- **helpers.py syntax fixed** — `monthly_values[max(0, i - 11): i + 1]` (v1 had `monthly_valuesax(0, i - 11): i + 1]`).
- **5 descriptive PT-BR tab names** — Resumo, Juros, Inflacao, Cambio, Atividade (per user request: "on side bar - menu, just generic names").
- **TR (226) added to rates mode** — was dropped in v2.

### Dashboard Tabs (5)

| Tab | Name | Group | Content |
|-----|------|-------|---------|
| 1 | Resumo | Resumo | Text overview. |
| 2 | Juros | Indicadores | rates mode sections (5 series). |
| 3 | Inflacao | Indicadores | inflation mode sections (2 series). |
| 4 | Cambio | Indicadores | fx mode sections (2 series). |
| 5 | Atividade | Indicadores | PIB + Salario minimo (chart + table). |

### KPI Cards (4, top-level)

| KPI | Series | Unit | v3 fix |
|-----|--------|------|--------|
| Selic (anualizada) | 11 | % a.a. | (unchanged from v2) |
| CDI (diaria) | 12 | % a.d. | **daily, NOT annualized** |
| IPCA (mes) | 433 | % | (unchanged) |
| USD/BRL (ptax) | 1 | R$ | (unchanged) |

### Modes (4)

dashboard, rates, inflation, fx.

---

## v2.0 — 2026-07-23

(Replaced by v3 — see v2 zip for details. Key issues: `label` instead of `name`, per-tab KPIs, separate `labels`/`values` arrays instead of `chart_data`, list-of-dicts table rows, CDI annualized, missing TR 226, helpers.py syntax error.)

---

*Last updated: 2026-07-24 (v3.0).*
