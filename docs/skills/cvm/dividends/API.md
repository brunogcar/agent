<- Back to [CVM Skills](../../)

# 📖 API Reference — dividends skill

## skill(domain="cvm", sub_domain="dividends", ...)

### mode="history"

Individual dividend events from B3 (rate, dates, label).

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | B3 ticker (PETR4) |
| limit | int | no | Max events. Default: 50 |

```json
{
  "status": "ok",
  "ticker": "PETR4",
  "count": 2,
  "dividends": [
    {"label": "JCP", "approved_on": "2024-08-15", "rate": 0.35,
     "payment_date": "2024-09-15", "related_to": "2T2024"}
  ]
}
```

### mode="annual"

Annual declared totals from DFP DVA 7.08.04.* per fiscal year.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | Ticker, name, or CNPJ |
| periods | int | no | Number of fiscal years. Default: 5 |

### mode="payable"

Dividends declared but not yet paid (DFP BPP 2.01.05.02.01).

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | Ticker, name, or CNPJ |
| periods | int | no | Number of fiscal years. Default: 5 |

### mode="announcements"

Official CVM IPE filings related to dividends (keyword "dividendo").

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | no | Company name, CNPJ, or ticker. Empty = all |
| limit | int | no | Max results. Default: 20 |

### mode="summary"

Combined: recent events + annual trend + last payable. Best-effort.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | Ticker preferred (covers all sources) |

---

## Examples

```
skill(domain="cvm", sub_domain="dividends", mode="history", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="dividends", mode="annual", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="dividends", mode="summary", params='{"company":"VALE3"}')
```

---

*Last updated: 2026-07-23 (v1.0).*
