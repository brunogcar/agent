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

## Tool Invocation

```python
skill(domain="cvm", sub_domain="governance", mode="practices", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="score", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="governance", mode="by_chapter", params='{"company":"PETR4"}')
```

## Report Adapters

| Adapter | Source mode | What it tables |
|---|---|---|
| `governance_practices` | practices | Practices table (item, chapter, recommended, adopted, explanation) |
| `governance_score` | score | KPI strip (score %, adopted, partial, not adopted) + summary table |
| `governance_by_chapter` | by_chapter | Per-chapter adoption table (total, adopted, partial, not adopted, score %) |

---

*Last updated: 2026-07-25 (v1.0).*
