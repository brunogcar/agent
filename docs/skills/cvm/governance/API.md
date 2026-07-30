<- Back to [GOVERNANCE Overview](../GOVERNANCE.md)

# 📝 API Reference

## Modes

### `mode="practices"` (default)
All governance practices for the latest filing (recommended vs adopted).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |

### `mode="score"`
Governance score: % of practices adopted (Sim), partial (Parcialmente), not adopted (Não).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |

Returns: `{status, company, total_practices, adopted_sim, adopted_nao, adopted_parcialmente, score_pct, partial_pct, not_adopted_pct, data_freshness}`

### `mode="by_chapter"`
Practices grouped by chapter (Capitulo) with adoption counts.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |

### `mode="dashboard"` (v1.1)
Multi-tab dashboard payload for the report tool. Pipes into the `governance_dashboard` adapter (report tool v1.7, 70th adapter) which renders tabs: Overview (score KPIs) + Practices + By Chapter.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |

## Tool Invocation

```python
skill(domain="cvm", sub_domain="governance", mode="practices", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="score", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="by_chapter", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="dashboard", params='{"company":"PETR4"}')
```

## Report Adapters

| Adapter | Source mode | What it tables |
|---|---|---|
| `governance_practices` | practices | Practices table (item, chapter, recommended, adopted, explanation) |
| `governance_score` | score | KPI strip (score %, adopted, partial, not adopted) + summary table |
| `governance_by_chapter` | by_chapter | Per-chapter adoption table (total, adopted, partial, not adopted, score %) |
| `governance_dashboard` (v1.1) | dashboard | **Dashboard adapter** — multi-tab dashboard (Overview KPIs + Practices + By Chapter). Thin pass-through of the `governance.dashboard()` tab payload |

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; modes + params + return shapes unchanged). See [ARCHITECTURE.md](ARCHITECTURE.md) for the updated source code reference.*
