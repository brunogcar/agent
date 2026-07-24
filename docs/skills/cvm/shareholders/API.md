<- Back to [SHAREHOLDERS Overview](../SHAREHOLDERS.md)

# 📖 API Reference — shareholders skill

## skill(domain="cvm", sub_domain="shareholders", ...)

### mode="shareholders"

Named shareholders with ownership % from FRE.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | B3 ticker (PETR4), name fragment, or CNPJ |
| limit | int | no | Max shareholders. Default: 50 |

```json
{
  "status": "ok",
  "company": "PETROLEO BRASILEIRO S.A.",
  "cnpj": "33000167000101",
  "data_referencia": "2023-12-31",
  "shareholders": [
    {"acionista": "UNIAO FEDERAL", "cpf_cnpj": "00000000000001",
     "tipo_pessoa": "PJ", "controlador": "S",
     "pct_on": 36.7, "pct_pn": 0.0, "pct_total": 28.9}
  ]
}
```

### mode="free_float"

Free float % + shareholder counts from FRE.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | Ticker, name, or CNPJ |

### mode="equity_structure"

Equity breakdown in BRL from DFP BPP 2.03.* over N periods.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | Ticker, name, or CNPJ |
| periods | int | no | Number of fiscal years. Default: 5 |

Returns per period: total PL (2.03) + capital social (2.03.01) + reservas (2.03.02, 2.03.04) + lucros acumulados (2.03.05) + minority interest (2.03.09).

### mode="summary"

Combined: top shareholders + free float + latest equity total. Best-effort — if one source is missing, returns what's available.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | Ticker, name, or CNPJ |

---

## Examples

```
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params='{"company":"VALE3","periods":3}')
skill(domain="cvm", sub_domain="shareholders", mode="summary", params='{"company":"PETR4"}')
```

---

*Last updated: 2026-07-23 (v1.0).*
