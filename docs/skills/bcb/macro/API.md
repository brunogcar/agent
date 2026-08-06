<- Back to [MACRO](../MACRO.md)

# 📡 Macro API — 4 Modes

## 1. `dashboard`

5-tab BCB macro dashboard. Composes `rates` + `inflation` + `fx` modes + a thin Atividade tab. Top-level KPIs (Selic anualizada, CDI diaria, IPCA mes, USD/BRL ptax).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `days` | int | 30 | Daily-series window. |
| `months` | int | 12 | Monthly-series window. |

```python
skill(domain="bcb", sub_domain="macro", mode="dashboard")
skill(domain="bcb", sub_domain="macro", mode="dashboard", params='{"days":90,"months":24}')
```

Returns:
```python
{
    "status": "ok",
    "mode": "dashboard",
    "tabs": [
        {"name": "Resumo",    "group": "Resumo",      "sections": [...]},
        {"name": "Juros",     "group": "Indicadores", "sections": [...]},
        {"name": "Inflacao",  "group": "Indicadores", "sections": [...]},
        {"name": "Cambio",    "group": "Indicadores", "sections": [...]},
        {"name": "Atividade", "group": "Indicadores", "sections": [...]},
    ],
    "kpis": [
        {"label": "Selic (anualizada)", "value": "13.15%", ...},
        {"label": "CDI (diaria)",       "value": "0.001235%", ...},
        {"label": "IPCA (mes)",         "value": "0.42%", ...},
        {"label": "USD/BRL (ptax)",     "value": "R$ 4,9480", ...},
    ],
    "errors": [],
}
```

**v3 fixes:**
- Tab field is `name` (was `label`).
- KPIs are at top level (was per-tab).
- CDI KPI shows daily rate `% a.d.` (was annualized).
- Chart sections have `chart_data` (Chart.js config).
- Table rows are list of lists.

---

## 2. `rates`

BCB interest-rate dashboard. 5 series: Selic diaria (11), CDI diaria (12), TR (226), Meta Copom (432), Selic acumulada (4389). KPIs annualize `% a.d.` → `% a.a.` (× 252).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `days` | int | 30 | Number of most-recent obs per series. |

```python
skill(domain="bcb", sub_domain="macro", mode="rates")
skill(domain="bcb", sub_domain="macro", mode="rates", params='{"days":90}')
```

Returns: `{"status": "ok", "mode": "rates", "kpis": [...], "sections": [...]}`

Each series produces: 1 KPI card + 1 chart section + 1 table section (last 10 obs).

---

## 3. `inflation`

BCB inflation dashboard. 2 series: IPCA mensal (433), IGP-M mensal (189). KPIs show latest monthly variation + rolling 12-month acumulado.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `months` | int | 12 | Number of most-recent monthly obs. |

```python
skill(domain="bcb", sub_domain="macro", mode="inflation")
skill(domain="bcb", sub_domain="macro", mode="inflation", params='{"months":24}')
```

Returns: `{"status": "ok", "mode": "inflation", "kpis": [...], "sections": [...]}`

Each series produces: 1 KPI card (latest + acum 12m) + 1 chart section (monthly variation) + 1 table section (12m acumulado, last 12 rows).

---

## 4. `fx`

BCB exchange-rate dashboard. 2 series: USD/BRL ptax venda diaria (1), USD/BRL ptax mensal (24369). KPI shows latest ptax + min/max/mean stats.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `days` | int | 30 | Number of most-recent daily obs. |

```python
skill(domain="bcb", sub_domain="macro", mode="fx")
skill(domain="bcb", sub_domain="macro", mode="fx", params='{"days":90}')
```

Returns: `{"status": "ok", "mode": "fx", "kpis": [...], "sections": [...]}`

Daily series produces: 1 KPI card (latest + min/max/mean) + 1 chart + 1 table (last 10). Monthly series produces: 1 chart + 1 table (last 12).

---

*Last updated: 2026-08-06 (v3.1).*
