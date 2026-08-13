<- Back to [PRICE Overview](../PRICE.md)

# 📖 API Reference

## skill(domain="b3", sub_domain="price", ...)

### mode="dashboard" (default)

5-tab price analytics dashboard: candlestick + MA + volume + returns + volatility.

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
    {"name": "Retornos",      "group": "Performance", "sections": [{"type": "chart", ...}, {"type": "chart", ...}, {"type": "table", ...}]},
    {"name": "Volatilidade",  "group": "Performance", "sections": [{"type": "chart", ...}, {"type": "chart", ...}, {"type": "table", ...}]}
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

**Tabs (5):**
| Tab | Group | Sections |
|-----|-------|----------|
| Cotação | Preço | text header + candlestick chart + volume bar chart |
| Médias Móveis | Preço | SMA line chart + crossovers table |
| Volume | Preço | volume bar chart (colored by up/down day) + volume MA20 line + statistics table |
| Retornos | Performance | cumulative return chart + drawdown chart + performance summary table |
| Volatilidade | Performance | rolling volatility chart (20D/60D/252D) + Bollinger Bands chart + current vol table |

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

*Last updated: 2026-08-06 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
