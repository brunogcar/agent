<- Back to [INVESTSITE Overview](../INVESTSITE.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `skills/investsite/__init__.py` | MANIFEST + route (flat domain, 5 modes) |
| `skills/investsite/fetcher.py` | HTTP fetch (httpx + browser headers), in-memory cache (1h TTL), rate limiting (0.5s), URL builders |
| `skills/investsite/parsers.py` | HTML table extraction: `parse_indicators()`, `parse_statement()`, `parse_events()` |
| `skills/investsite/investsite.py` | Mode logic: indicators, statements, events, summary, listing |

## Data Flow

```
skill(domain="investsite", mode="indicators", params='{"ticker":"PETR4"}')
  │
  ▼  fetcher.fetch_page("principais_indicadores.php", {"cod_negociacao": "PETR4"})
  │    → httpx GET with browser headers
  │    → cache check (1h TTL) → cache hit = return cached HTML
  │    → rate limit (0.5s) → fetch → cache store → return HTML
  │
  ▼  parsers.parse_indicators(html)
  │    → extract 10 <table> elements
  │    → match <caption> to section keys
  │    → parse rows as key-value pairs
  │    → return {sections: {dados_basicos, precos_relativos, ...}}
```

## URL Patterns

| Mode | URL |
|------|-----|
| indicators | `principais_indicadores.php?cod_negociacao={ticker}` |
| statements (BPA) | `balanco_patrimonial_ativo.php?cod_negociacao={ticker}` |
| statements (BPP) | `balanco_patrimonial_passivo.php?cod_negociacao={ticker}` |
| statements (DRE) | `demonstracao_resultado.php?cod_negociacao={ticker}` |
| statements (DFC) | `fluxo_caixa.php?cod_negociacao={ticker}` |
| statements (DVA) | `demonstracao_valor_adicionado.php?cod_negociacao={ticker}` |
| statements (shares) | `quantidade_acoes.php?cod_negociacao={ticker}` |
| events | `informacoes_periodicas_detalhe.php?cod_negociacao={ticker}&categoria={cat}` |

## Goldmine Indicators (for b3-api improvement)

The investsite main page computes these indicators that we should add to `data_sources/b3/api` or a new skill:

### Valuation Ratios (Preços Relativos)
| Indicator | What |
|-----------|------|
| Preço/Lucro (P/L) | Price-to-Earnings |
| Preço/VPA (P/B) | Price-to-Book |
| Preço/Receita Líquida (P/S) | Price-to-Sales |
| Preço/FCO | Price-to-Operating-Cash-Flow |
| Preço/FCF | Price-to-Free-Cash-Flow |
| Preço/Ativo Total | Price-to-Total-Assets |
| Preço/EBIT | Price-to-EBIT |
| Market Cap | Market capitalization |
| Enterprise Value (EV) | EV = Market Cap + Debt - Cash |
| Dividend Yield | Annual dividends / Price |

### Returns & Margins (Retornos e Margens)
| Indicator | What |
|-----------|------|
| ROE | Return on Equity |
| ROA | Return on Assets |
| ROIC | Return on Invested Capital |
| Margem Bruta | Gross margin |
| Margem Líquida | Net margin |
| Margem EBIT | EBIT margin |
| Margem EBITDA | EBITDA margin |
| Giro do Ativo | Asset turnover |
| Alavancagem Financeira | Financial leverage |
| Passivo/PL | Debt-to-equity |
| Dívida Líquida/EBITDA | Net debt / EBITDA |

### Experimental
| Indicator | What |
|-----------|------|
| CAPEX (3M, 12M) | Capital expenditure |
| Fluxo de Caixa Livre (3M, 12M) | Free cash flow = FCO - CAPEX |

## Parser Design

### Table extraction
The parser handles two table types:
- **Tables with `<th>` headers** — first row treated as headers, rest as data
- **Tables with only `<td>`** — all rows are data (no headers stripped)

### Events link extraction
The events page has links inside `<td>` cells (in the "Assuntos" column). The parser:
1. Finds the largest `<table>` block (the events table)
2. Extracts `<a href>` links per row
3. Pairs links with row data by index

## Modes

| Mode | Pages fetched | Returns |
|------|--------------|---------|
| `indicators` | 1 (main page) | 10 sections of key-value data |
| `statements` | 1 (per statement type) | Account codes + period values + % total |
| `events` | 1 (per category) | Events list with CVM PDF links |
| `summary` | 2 (indicators + events) | Key indicators + latest Fato Relevante |
| `listing` | 0 (static) | Available event categories |

---

*Last updated: 2026-07-24 (v1.0).*
