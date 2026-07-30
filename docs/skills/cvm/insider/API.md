<- Back to [INSIDER Overview](../INSIDER.md)

# 📝 API Reference

## Modes

### `mode="history"` (default)
Recent insider transactions (newest-first).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |
| `limit` | `int` | `50` | Max results |

Returns: `{status, company, cnpj, count, movements[], data_freshness}` where each movement has `Data_Movimentacao`, `Tipo_Cargo`, `Tipo_Movimentacao`, `Tipo_Ativo`, `Quantidade`, `Preco_Unitario`, `Volume`, `Descricao_Movimentacao`.

### `mode="by_role"`
Insider transactions grouped by role (Tipo_Cargo). Shows total bought/sold per role.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |
| `limit` | `int` | `50` | Max roles |

Returns: `{status, company, cnpj, count, by_role[], data_freshness}` where each role entry has `Tipo_Cargo`, `transaction_count`, `total_bought`, `total_sold`, `volume_bought`, `volume_sold`, `earliest_date`, `latest_date`.

### `mode="summary"`
Net buy/sell summary per month (last 24 months). Shows insider sentiment trend.

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |

Returns: `{status, company, cnpj, count, monthly[], sentiment, net_volume, total_volume_bought, total_volume_sold, data_freshness}` where each monthly entry has `month`, `transaction_count`, `bought`, `sold`, `volume_bought`, `volume_sold`, `net_shares`, `net_volume`. `sentiment` is `"buying"` / `"selling"` / `"neutral"`.

### `mode="dashboard"` (v1.1)
Multi-tab dashboard composition (thin composition of `summary()` + `history()` + `by_role()`).

| Param | Type | Default | Description |
|---|---|---|---|
| `company` | `str` | (required) | Ticker, name, or CNPJ |

Returns:
```python
{
    "status": "ok",
    "company": "PETR4",
    "tabs": [
        {"name": "Overview",            "sections": [<Summary text>]},
        {"name": "Recent Transactions", "sections": [<7-col table: Data, Cargo, Tipo, Ativo, Qtd, Preço, Volume — limited to 10 most recent>]},
        {"name": "By Role",             "sections": [<7-col table: Cargo, Transações, Qtd Comprada, Qtd Vendida, Vol Comprado, Vol Vendido, Net Volume>]},
        {"name": "Monthly Net",         "sections": [<7-col table: Mês, Transações, Comprado, Vendido, Vol Comprado, Vol Vendido, Net Volume>]},
    ],
    "kpis": [
        {"label": "Sentimento",      "value": "BUYING",      "unit": "text"},
        {"label": "Volume Comprado", "value": "R$ 385,00 K", "unit": "brl"},
        {"label": "Volume Vendido",  "value": "R$ 189,00 K", "unit": "brl"},
        {"label": "Net Volume",      "value": "R$ 196,00 K", "unit": "brl"},
    ],
}
```

Behavior:
- The dashboard short-circuits before any underlying skill is called when `company` is empty (`{"status": "error", "error": "company is required"}`).
- Each sub-call (`summary()` / `history()` / `by_role()`) is independently `try/except`-wrapped — a missing VLMO DB or a query-engine exception degrades the corresponding tab to an error payload (table with 0 rows) and KPIs render as `"—"` instead of crashing the whole dashboard.
- Top-level `company` field prefers `summary()`'s resolved company; falls back to `history()` → `by_role()` → input company.

## Tool Invocation

```python
skill(domain="cvm", sub_domain="insider", mode="history", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="insider", mode="by_role", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="insider", mode="summary", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="insider", mode="dashboard", params='{"company":"PETR4"}')
```

## Report Adapters

| Adapter | Source mode | What it tables |
|---|---|---|
| `insider_history` | history | Transactions table (date, role, type, qty, price, volume) |
| `insider_by_role` | by_role | Per-role summary (bought/sold/net per role) |
| `insider_summary` | summary | Monthly net table + KPI strip (sentiment, volumes, net) |
| `insider_dashboard` | dashboard | Multi-tab dashboard (Overview text + 3 tables + 4 top-level KPI cards) |

---

*Last updated: 2026-07-25 (v1.1).*
