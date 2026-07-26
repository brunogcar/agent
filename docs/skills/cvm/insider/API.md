<- Back to [INSIDER Overview](../INSIDER.md)

# 📝 API Reference

## Modes

### `mode="history"` (default)
Recent insider transactions (newest-first).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |
| `limit` | `int` | `50` | Max results |

### `mode="by_role"`
Insider transactions grouped by role (Tipo_Cargo). Shows total bought/sold per role.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |
| `limit` | `int` | `50` | Max roles |

### `mode="summary"`
Net buy/sell summary per month (last 24 months). Shows insider sentiment trend.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |

Returns: `{status, company, monthly, sentiment, net_volume, total_volume_bought, total_volume_sold, data_freshness}`

## Tool Invocation

```python
skill(domain="cvm", sub_domain="insider", mode="history", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="insider", mode="by_role", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="insider", mode="summary", params='{"company":"PETR4"}')
```

## Report Adapters

| Adapter | Source mode | What it tables |
|---|---|---|
| `insider_history` | history | Transactions table (date, role, type, qty, price, volume) |
| `insider_by_role` | by_role | Per-role summary (bought/sold/net per role) |
| `insider_summary` | summary | Monthly net table + KPI strip (sentiment, volumes, net) |

---

*Last updated: 2026-07-25 (v1.0).*
