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

### mode="dashboard" (v1.1)

Multi-tab dashboard payload for the report tool. Pipes into the `shareholders_dashboard` adapter (73rd adapter) which renders 4 tabs: Overview (Summary text + 3 top-level KPI cards: % Free Float, Total Acionistas, PL Total), Top Shareholders (table: Acionista, % Total, Qtde Total, Controlador), Free Float (single-row table: % Free Float, Acionistas PF/PJ/Inst.), Equity Structure (table: Componente, Valor BRL — BPP 2.03.* components).

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| company | str | yes | Ticker, name, or CNPJ |

Returns a structured payload `{"status": "ok", "company": ..., "tabs": [...], "kpis": [...]}` where each tab is `{"name": str, "sections": [...]}`. KPIs go at the top level (not inside a tab) so the dashboard template renders them above all tabs via the `kpi-grid` div.

The dashboard degrades gracefully: if `summary()` returns an error payload (e.g. FRE not synced, DFP not synced, company not in bridge), the dashboard still renders `status=ok` with 4 tabs — Top Shareholders + Equity Structure tabs have 0 rows, Free Float tab has 1 row of None values, all KPIs render as "—".

## Tool Invocation

```
skill(domain="cvm", sub_domain="shareholders", mode="shareholders", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="shareholders", mode="free_float", params='{"company":"VALE3"}')
skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="shareholders", mode="equity_structure", params='{"company":"VALE3","periods":3}')
skill(domain="cvm", sub_domain="shareholders", mode="summary", params='{"company":"PETR4"}')
skill(domain="cvm", sub_domain="shareholders", mode="dashboard", params='{"company":"PETR4"}')
```

## Report Adapters

| Adapter | Source mode | What it tables |
|---|---|---|
| `shareholders_shareholders` | shareholders | Named shareholders table (Acionista, CPF/CNPJ, Tipo, % ON/PN/Total, Qtde, Controlador) |
| `shareholders_free_float` | free_float | Free float table (Data Referência, % Circulação, PF/PJ/Inst. counts) |
| `shareholders_equity_structure` | equity_structure | Equity per period table (Período + 6 BPP 2.03.* component columns) |
| `shareholders_summary` | summary | KPI strip + top shareholders + equity components |
| `shareholders_dashboard` (v1.1) | dashboard | **Dashboard adapter** — multi-tab dashboard (Overview KPIs + Top Shareholders + Free Float + Equity Structure). Thin pass-through of the `shareholders.dashboard()` tab payload |

---

*Last updated: 2026-07-30 (v2.0 — `skills/_base.py` extraction; modes + params + return shapes unchanged). See [ARCHITECTURE.md](ARCHITECTURE.md) for the updated source code reference.*
