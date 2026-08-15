<- Back to [PRICE Overview](../PRICE.md)

# 📖 API Reference

## skill(domain="b3", sub_domain="price", ...)

### mode="dashboard" (default)

6-tab price analytics dashboard: candlestick + MA + volume + indicators + returns + volatility.

[v1.3] Now 7 tabs — added "Fibonacci" tab (Análise Técnica group) + dividend-adjusted returns in the Retornos tab.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| ticker | str | — | B3 ticker (PETR4, VALE3, etc.). Required |
| skip_sync | bool | False | Bypass sync guard (no freshness check, no force-sync) |

**Response shape:**
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "title": "Price Dashboard — PETR4",
  "kpis": [
    {"type": "kpi", "label": "Preço",          "value": "R$ 38,50", "delta": "+1,26%"},
    {"type": "kpi", "label": "Variação (dia)", "value": "1,26%",    "subtitle": "vs. fechamento anterior"},
    {"type": "kpi", "label": "Abertura",       "value": "R$ 38,20"},
    {"type": "kpi", "label": "Máxima",         "value": "R$ 38,80", "subtitle": "52s: R$ 28,00 – R$ 40,20"},
    {"type": "kpi", "label": "Mínima",         "value": "R$ 38,10"},
    {"type": "kpi", "label": "Volume",         "value": "150,00 M", "unit": "R$", "subtitle": "20000 negócios"}
  ],
  "tabs": [
    {"name": "Cotação",       "group": "Preço",       "sections": [
       {"type": "text",        "title": "Cotação — PETR4", "text": "Período: ... • ... pregões • Fonte: B3 COTAHIST"},
       {"type": "candlestick", "title": "Candlestick — PETR4",
        "chart_data": {"type": "candlestick", "data": {"labels": [...], "datasets": [
           {"type": "candlestick", "label": "PETR4", "data": [{"t": "2024-01-02", "o": 38.0, "h": 38.5, "l": 37.8, "c": 38.2}, ...]},
           {"type": "line", "label": "MA20",  "data": [...], "borderColor": "#facc15"},
           {"type": "line", "label": "MA50",  "data": [...], "borderColor": "#fb923c"},
           {"type": "line", "label": "MA100", "data": [...], "borderColor": "#ec4899"},
           {"type": "line", "label": "MA200", "data": [...], "borderColor": "#ef4444"}
        ]}},
        "price_range_selector": true, "price_full_labels": [...], "price_full_data": [...]}
    ]},
    {"name": "Médias Móveis", "group": "Preço",       "sections": [
       {"type": "chart", "title": "Médias Móveis — PETR4", ...},
       {"type": "table", "title": "Cruzamentos de Médias", "columns": [...], "rows": [...]}
    ]},
    {"name": "Volume",        "group": "Preço",       "sections": [{"type": "chart", ...}, {"type": "table", ...}]},
    {"name": "Indicadores",  "group": "Preço",       "sections": [
       {"type": "chart", "title": "Preço — PETR4", ...},
       {"type": "chart", "title": "RSI (14) — PETR4", "collapsible": true, ...},
       {"type": "chart", "title": "MACD (12/26/9) — PETR4", "collapsible": true, ...},
       {"type": "chart", "title": "Stochastic (14/3/3) — PETR4", "collapsible": true, ...},
       {"type": "chart", "title": "On-Balance Volume (OBV) — PETR4", "collapsible": true, ...},
       {"type": "table", "title": "Sinais Atuais", "columns": ["Indicador", "Valor Atual", "Sinal"], ...}
    ]},
    {"name": "Retornos",      "group": "Performance",       "sections": [{"type": "chart", ...}, {"type": "chart", ...}, {"type": "chart", ...}, {"type": "table", ...}]},
    {"name": "Volatilidade",  "group": "Performance",       "sections": [{"type": "chart", ...}, {"type": "chart", ...}, {"type": "table", ...}]},
    {"name": "Fibonacci",     "group": "Análise Técnica",  "sections": [
       {"type": "table", "title": "Níveis de Fibonacci — Swing_4 (4 semanas / 1 mês)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Níveis de Fibonacci — Swing_12 (12 semanas / 3 meses)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Níveis de Fibonacci — Swing_52 (52 semanas / 1 ano)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Trade Setup — COMPRA — Swing_4 (4 semanas / 1 mês)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Trade Setup — COMPRA — Swing_12 (12 semanas / 3 meses)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Trade Setup — COMPRA — Swing_52 (52 semanas / 1 ano)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Trade Setup — VENDA — Swing_4 (4 semanas / 1 mês)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Trade Setup — VENDA — Swing_12 (12 semanas / 3 meses)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Trade Setup — VENDA — Swing_52 (52 semanas / 1 ano)", "collapsible": true, "collapsible_open": true, ...},
       {"type": "table", "title": "Ajuste de Proventos", ...}
    ]}
  ],
  "period": {"from": "2014-08-06", "to": "2024-08-06", "days": 2480},
  "crossovers": {"ma20_x_ma50": 12, "ma50_x_ma200": 3},
  "html_path": "/workspace/reports/PETR4_price_dashboard.html"
}
```

**KPI cards (6):**
- **Preço** — latest close (with `delta` showing variation vs prior close)
- **Variação (dia)** — % change vs prior close
- **Abertura** — latest day open
- **Máxima** — latest day high (subtitle shows 52-week range)
- **Mínima** — latest day low
- **Volume** — latest day financial volume (compact, R$ suffix)

**Tabs (7):**
| Tab | Group | Sections |
|-----|-------|----------|
| Cotação | Preço | text header + candlestick chart + volume bar chart |
| Médias Móveis | Preço | SMA line chart + crossovers table |
| Volume | Preço | volume bar chart (colored by up/down day) + price overlay + statistics table |
| Indicadores | Preço | price reference chart + RSI + MACD + Stochastic + OBV (collapsible) + signals table |
| Retornos | Performance | cumulative return chart + (adjusted return chart) + drawdown chart + KPI table |
| Volatilidade | Performance | rolling volatility chart (20D/60D/252D) + Bollinger Bands chart + current vol table |
| Fibonacci | Análise Técnica | 9 collapsible tables (grouped by swing: Níveis collapsed + COMPRA + VENDA per swing) + dividend adjustments table |

**Fibonacci tab (v1.3 — 10 sections, grouped by swing):**

Sections are organized BY SWING (not by category): for each swing (Swing_4 → Swing_12 → Swing_52), 3 collapsible tables:
- **Níveis de Fibonacci — Swing_X** (collapsed by default) — all 11 Fibonacci levels (0.236 through 4.236) + their prices. The timeframe desc (e.g. "4 semanas / 1 mês") appears once in the description, not in the title.
- **Trade Setup — COMPRA — Swing_X** (expanded by default) — Entrada 1 (0.382), Entrada 2 (0.618), Alvo 1 (0.382 extension), Alvo 2 (0.618 extension), STOP. Shows % distance from current price.
- **Trade Setup — VENDA — Swing_X** (expanded by default) — mirrored from COMPRA (uses swing low).

Then 1 non-collapsible table:
- **Ajuste de Proventos** — cash dividends applied during the period, filtered by the ticker's ISIN.

**Collapsible tables:** the 9 Fibonacci tables have `collapsible: True`. Níveis tables have `collapsible_open: False` (collapsed by default — reference info). COMPRA + VENDA tables have `collapsible_open: True` (expanded by default — actionable info). Click any table header to toggle.

**Note on chart:** the Fibonacci chart was removed in v1.3 — the chart needs daily-data infrastructure that's not ready yet. Will be added in a future commit when daily data saving is implemented.

**Retornos tab (v1.3 addition):** the Retornos tab now includes a **dividend-adjusted cumulative return chart** (purple line) alongside the raw return chart. The adjusted return uses backward-adjusted close prices (historical prices minus dividends paid after that date), giving the true total return including reinvested dividends. The KPI table adds a "Retorno Cumulativo Ajustado" row.

**Indicadores tab (v1.2 — 6 sections):**
- **Preço (reference)** — single-axis close-price line chart at the top. Not collapsible (always visible). The user looks at this once, then scrolls through the indicators.
- **RSI (14)** — Wilder's smoothing RSI, 0-100, with dashed 30/70 overbought/oversold reference lines. Single axis. Collapsible.
- **MACD (12/26/9)** — histogram bars (green/red by sign) + MACD line + signal line. Single axis. Collapsible.
- **Stochastic (14/3/3)** — %K + %D lines, 0-100, with dashed 20/80 reference lines. Single axis. Collapsible.
- **OBV** — On-Balance Volume cumulative signed volume (filled purple line). Single axis. Collapsible.
- **Signals table** — 4-row table classifying the latest reading of each indicator (Overbought/Neutral/Oversold, Bull/Bear trend).

**Collapsible charts:** the 4 indicator charts have `collapsible: True` — the chart title becomes a clickable header (expand/collapse). A `toggleChartCollapsible` JS function resizes the chart on expand so it renders with correct dimensions (charts rendered while collapsed had 0-height canvases). The price reference chart is NOT collapsible (always visible at the top).

### mode="quote"

Latest OHLCV snapshot + 52-week high/low. Compact response — no charts.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| ticker | str | — | B3 ticker. Required |
| skip_sync | bool | False | Bypass sync guard |

**Response shape:**
```json
{
  "status": "ok",
  "ticker": "PETR4",
  "quote": {
    "date": "2024-08-06", "open": 38.20, "high": 38.80, "low": 38.10,
    "close": 38.50, "volume": 150000000, "trade_count": 20000
  },
  "range_52w": {"high_52w": 42.10, "low_52w": 28.00},
  "prev_close": 38.20,
  "kpis": [
    {"type": "kpi", "label": "Preço",          "value": "R$ 38,50", "delta": "+0,78%"},
    {"type": "kpi", "label": "Variação (dia)", "value": "0,78%"},
    {"type": "kpi", "label": "Abertura",       "value": "R$ 38,20"},
    {"type": "kpi", "label": "Máxima",         "value": "R$ 38,80", "subtitle": "52s: R$ 28,00 – R$ 42,10"},
    {"type": "kpi", "label": "Mínima",         "value": "R$ 38,10"},
    {"type": "kpi", "label": "Volume",         "value": "150,00 M", "unit": "R$"}
  ]
}
```

## Examples

```
skill(domain="b3", sub_domain="price", mode="dashboard", params='{"ticker":"PETR4"}')
skill(domain="b3", sub_domain="price", mode="quote",     params='{"ticker":"VALE3"}')
```

## Error Responses

```json
// Missing ticker
{"status": "error", "error": "ticker is required"}

// No data for ticker
{"status": "error", "ticker": "ZZZZ9", "error": "no OHLCV data for ZZZZ9 in 2014-08-06..2024-08-06"}

// Unknown mode
{"status": "error", "error": "Unknown mode 'history'. Available: ['dashboard', 'quote']"}

// Missing mode
{"status": "error", "error": "mode required. Options: ['dashboard', 'quote']"}
```

---

*Last updated: 2026-08-15 (v1.4 — Cotação tab redesign). See [CHANGELOG.md](CHANGELOG.md) for version history.*
