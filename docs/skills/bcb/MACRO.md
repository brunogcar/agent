<- Back to [BCB Skills](../BCB.md)

# 📊 MACRO — Brazilian Macro-Economic Dashboard

BCB macro skill. 4 modes: `dashboard` (5-tab), `rates`, `inflation`, `fx`. Reads from `data_sources/bcb/sgs/query_engine.py` (read-only — no own DB).

## Modes

| Mode | Description | include_in_all |
|------|-------------|----------------|
| [dashboard](macro/API.md#1-dashboard) | 5-tab: Resumo / Juros / Inflacao / Cambio / Atividade. Top-level KPIs + per-tab charts + tables. | No |
| [rates](macro/API.md#2-rates) | Selic / CDI / TR / Meta Copom / Selic acumulada. KPIs annualize % a.d. → % a.a. | Yes |
| [inflation](macro/API.md#3-inflation) | IPCA + IGP-M with rolling 12-month acumulado. | Yes |
| [fx](macro/API.md#4-fx) | USD/BRL ptax diaria + mensal with min/max/mean stats. | Yes |

---

## Dashboard Tabs (5)

| Tab | Name | Group | Content |
|-----|------|-------|---------|
| 1 | Resumo | Resumo | Text overview + top-level KPIs (Selic anualizada, CDI diaria, IPCA mes, USD/BRL ptax). |
| 2 | Juros | Indicadores | Rates mode sections: 5 series × (chart + table). |
| 3 | Inflacao | Indicadores | Inflation mode sections: IPCA + IGP-M × (chart + table). |
| 4 | Cambio | Indicadores | FX mode sections: USD/BRL diaria + mensal × (chart + table). |
| 5 | Atividade | Indicadores | PIB nominal + Salario minimo × (chart + table). |

---

## KPI Cards (top-level, 4)

| KPI | Series | Unit | Note |
|-----|--------|------|------|
| Selic (anualizada) | 11 | % a.a. | Daily rate × 252. |
| CDI (diaria) | 12 | % a.d. | **v3: daily rate, NOT annualized** (per user request). |
| IPCA (mes) | 433 | % | Latest monthly variation. |
| USD/BRL (ptax) | 1 | R$ | Latest ptax venda. |

---

## 🚀 Quick Start

```python
# Prerequisite: sync SGS data
data_source(domain="bcb", sub_domain="sgs", mode="sync_all")

# Full dashboard
skill(domain="bcb", sub_domain="macro", mode="dashboard")

# Focused modes
skill(domain="bcb", sub_domain="macro", mode="rates", params='{"days":90}')
skill(domain="bcb", sub_domain="macro", mode="inflation", params='{"months":24}')
skill(domain="bcb", sub_domain="macro", mode="fx", params='{"days":30}')
```

---

## ⚙️ Configuration

| Setting | Value |
|---------|-------|
| Data source | `data_sources/bcb/sgs/query_engine.py` (read-only) |
| Storage | Read-only — no own database |
| Required sources | `["sgs"]` (sync guard) |
| Skill pattern | Modular (`_registry.py` + `helpers.py` + `report.py` + `modes/`) |

---

## 📁 Subfile Directory

| File | Purpose |
|------|---------|
| [API.md](macro/API.md) | 4 modes documented with params + examples |
| [ARCHITECTURE.md](macro/ARCHITECTURE.md) | File map, mode dispatch flow, design decisions |
| [CHANGELOG.md](macro/CHANGELOG.md) | Version history (v3.0) |
| [INSTRUCTIONS.md](macro/INSTRUCTIONS.md) | AI editing rules — what NOT to break |
| [ROADMAP.md](macro/ROADMAP.md) | P2/P3 items |

---

*Last updated: 2026-07-24 (v3.0).*
