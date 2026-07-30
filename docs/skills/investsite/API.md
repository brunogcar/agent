<- Back to [INVESTSITE Overview](../INVESTSITE.md)

# 📖 API Reference

## skill(domain="investsite", ...)

### mode="indicators" (default)

Main page with 10 tables: basic data, prices/valuation, DRE TTM/quarterly, returns/margins, balance sheet, cash flow TTM/quarterly, experimental CAPEX/FCF.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| ticker | str | yes | B3 ticker (PETR4) |

Returns: `{status, ticker, sections: {dados_basicos, precos_relativos, dre_ttm, dre_quarterly, preco_volume, retornos_margens, balanco_patrimonial, fluxo_caixa_ttm, fluxo_caixa_quarterly, experimental}}`

### mode="statements"

Full financial statement with % total computed columns.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| ticker | str | — | Required |
| statement | str | "DRE" | BPA, BPP, DRE, DFC, DVA, shares |

Returns: `{status, ticker, statement_type, period_headers, accounts: [{codigo, descricao, periods: [{value, pct_total}]}], account_count}`

### mode="events"

Periodic info (IPE) by category with direct CVM rad.cvm.gov.br PDF links.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| ticker | str | — | Required |
| categoria | str | "" | Filter: Fato Relevante, Comunicado ao Mercado, etc. Empty = all |
| limit | int | 20 | Max events |

Returns: `{status, ticker, categoria, count, events: [{data_entrega, data_referencia, categoria, tipo, especie, assuntos, link_cvm}]}`

### mode="summary"

Combined: key indicators (prices, returns, balance, DRE TTM) + latest 10 Fato Relevante events.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| ticker | str | yes | B3 ticker |

### mode="listing"

List available event categories. No params required.

Returns: `{status, categories: ["Assembleia", "Aviso aos Acionistas", ...]}`

### mode="dashboard" (v1.1)

Multi-tab composition of `indicators()` + `events()`. Optimized for the report tool's dashboard action.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| ticker | str | yes | B3 ticker (PETR4) |

Returns: `{status, company, tabs: [...], kpis: [...]}` where each tab is `{name, sections: [...]}`.

Tabs:
- **Overview** — Summary text section (ticker, empresa, P/L, P/VPA, EV/EBITDA, ROE, Dividend Yield).
- **Key Indicators** — 2-column [Indicador, Valor] table flattening `precos_relativos` + `retornos_margens` (8 metric rows: P/L, P/VPA, EV/EBITDA, Dividend Yield, ROE, ROA, Margem EBITDA, Margem Líquida).
- **Latest Events** — 4-column [Data, Categoria, Descrição, Link] table of the 10 most recent Fato Relevante events with direct CVM rad.cvm.gov.br PDF links.

Top-level KPI cards (5, at the top level — not inside a tab):
- P/L (num)
- P/VPA (num)
- EV/EBITDA (num)
- ROE (pct)
- Dividend Yield (pct)

Each sub-call is independently try/except-wrapped so a network/parse failure degrades the corresponding tab to an empty payload (table has 0 rows, KPIs render as "—") instead of crashing the whole dashboard.

---

## Report Adapters

| Adapter | Serves |
|---------|-------|
| `investsite_dashboard` | [v1.1] `dashboard` mode — thin pass-through, re-formats KPIs via unit -> spec map. |

---

## Available Event Categories

| Category | Description |
|----------|-------------|
| Assembleia | Shareholder meetings |
| Aviso aos Acionistas | Shareholder notices |
| Comunicado ao Mercado | Market announcements |
| Dados Econômico-Financeiros | Economic-financial data |
| Fato Relevante | Relevant facts |
| Relatório Proventos | Dividend reports |
| Reunião da Administração | Board meetings |

---

## Examples

```
skill(domain="investsite", mode="indicators", params='{"ticker":"PETR4"}')
skill(domain="investsite", mode="statements", params='{"ticker":"VALE3","statement":"BPA"}')
skill(domain="investsite", mode="events", params='{"ticker":"PETR4","categoria":"Fato Relevante","limit":10}')
skill(domain="investsite", mode="summary", params='{"ticker":"PETR4"}')
skill(domain="investsite", mode="listing")
```

---

*Last updated: 2026-07-29 (v1.1).*
