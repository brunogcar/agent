<- Back to [OPTIONS Overview](../OPTIONS.md)

# 📖 API Reference

## skill(domain="b3", sub_domain="options", ...)

### mode="dashboard" (default + only mode)

3-tab B3 options analytics dashboard: options chain + put/call ratio +
volume by strike.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| underlying | str | `"PETR"` | 4-letter underlying code (e.g. `"PETR"`) or full ticker (`"PETR4"`). Trailing digits are stripped automatically. Required. |
| days | int | `90` | P/C ratio lookback window in trading days |
| skip_sync | bool | False | Bypass sync guard (no freshness check, no force-sync) |

**Response shape (success):**
```json
{
  "status": "ok",
  "underlying": "PETR",
  "title": "Options Dashboard — PETR",
  "tabs": [
    {
      "name": "Cadeia de Opções", "group": "Opções", "sections": [
        {"type": "text", "title": "Convenção de Ticker de Opções",
         "body": "Formato do ticker: UNDERLYING + MÊS + STRIKE ... (legend text)"},
        {"type": "table", "title": "Cadeia de Opções — PETR",
         "description": "N opções para o vencimento YYYY-MM-DD (ref: YYYY-MM-DD). Calls ordenadas por strike, seguidas de puts.",
         "columns": ["Papel", "Tipo", "Exercício", "Vencimento", "Último", "Volume", "Bid", "Ask"],
         "rows": [["PETRH36", "CALL", "R$ 36,00", "2026-08-17", "R$ 1,25", "12.345", "R$ 1,24", "R$ 1,26"], ...]}
      ]
    },
    {
      "name": "Put/Call Ratio", "group": "Análise", "sections": [
        {"type": "chart", "title": "Put/Call Ratio — PETR", "unit": "ratio",
         "description": "Razão Put/Call diária (90 pregões) — ...",
         "chart_data": {"type": "line", "data": {
           "labels": ["2026-05-01", "2026-05-02", ...],
           "datasets": [
             {"label": "Put/Call Ratio — PETR", "data": [0.82, 0.91, ...],
              "borderColor": "#22c55e", "fill": false, "tension": 0.3},
             {"label": "Referência (1,0)", "data": [1.0, 1.0, ...],
              "borderColor": "#9ca3af", "borderDash": [6, 4], "pointRadius": 0}
           ]},
           "options": {"responsive": true, "maintainAspectRatio": false, ...}},
         "price_range_selector": true,
         "price_full_labels": [...], "price_full_datasets": [...]},
        {"type": "table", "title": "Últimas Observações — PETR",
         "description": "Últimas 15 observações diárias (mais recente primeiro).",
         "columns": ["Data", "Volume Calls", "Volume Puts", "P/C Ratio"],
         "rows": [["2026-08-17", "1.234.567", "987.654", "0,8005"], ...]}
      ]
    },
    {
      "name": "Volume por Strike", "group": "Análise", "sections": [
        {"type": "chart", "title": "Volume por Strike — PETR",
         "description": "Volume financeiro (R$) por strike para o vencimento YYYY-MM-DD ...",
         "chart_data": {"type": "bar", "data": {
           "labels": ["R$ 30,00", "R$ 32,00", ...],
           "datasets": [
             {"label": "Calls", "data": [...], "backgroundColor": "#22c55e"},
             {"label": "Puts",  "data": [...], "backgroundColor": "#ef4444"}
           ]},
           "options": {"scales": {"y": {"beginAtZero": true, "title": {"text": "Volume (R$)"}}}}},
         "price_range_selector": true, ...},
        {"type": "table", "title": "Volume por Strike — PETR (detalhe)",
         "columns": ["Strike", "Vol. Calls", "Vol. Puts", "# Calls", "# Puts"],
         "rows": [["R$ 30,00", "123.456", "45.678", "3", "1"], ...]}
      ]
    }
  ],
  "html_path": "/workspace/reports/PETR_options_dashboard.html"
}
```

**Tabs (3):**

| Tab | Group | Sections |
|-----|-------|----------|
| Cadeia de Opções | Opções | ticker legend text + options chain table (Papel / Tipo / Exercício / Vencimento / Último / Volume / Bid / Ask) |
| Put/Call Ratio | Análise | daily P/C ratio line chart (green) + dashed grey reference line at 1.0 + latest 15 observations table |
| Volume por Strike | Análise | 2-dataset bar chart (calls green vs puts red) + per-strike detail table |

**Color convention:** Calls = green (`#22c55e`), Puts = red (`#ef4444`),
P/C reference line at 1.0 = dashed grey (`#9ca3af`).

**Nearest maturity auto-selection:** if the caller doesn't specify a
maturity, `options_chain` / `volume_by_strike` pick the nearest future
expiration date (or the most recent past one if no future maturities
exist). The selected maturity is returned in the response's tab sections.

## Examples

```
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR4"}')
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"VALE3","days":180}')
skill(domain="b3", sub_domain="options", mode="dashboard", params='{"underlying":"PETR"}')
```

## Error Responses

```json
// Missing underlying
{"status": "error", "error": "underlying is required"}

// Unknown mode
{"status": "error", "error": "Unknown mode 'chain'. Available: ['dashboard']"}

// Missing mode
{"status": "error", "error": "mode required. Options: ['dashboard']"}
```

**Graceful degradation:** if the `cotahist_derivatives` table is missing
(not synced), a sub-query returns `{"status": "not_synced", ...}` — the
dashboard stays `status=ok` and the affected tab renders an error section
(`"Erro ao consultar: ..."`) instead of the table/chart. The other tabs
still render. Only an empty/invalid `underlying` param returns a
top-level `status=error`.

Example partial-failure response (derivatives table not synced) —
dashboard stays `status=ok`, each tab renders an error section:
```json
{
  "status": "ok", "underlying": "PETR", "title": "Options Dashboard — PETR",
  "tabs": [
    {"name": "Cadeia de Opções", "group": "Opções", "sections": [
      {"type": "text", "title": "Convenção de Ticker de Opções", "body": "..."},
      {"type": "text", "title": "Cadeia de Opções",
       "body": "Erro ao consultar: FileNotFoundError: cotahist.db not found at ..."}
    ]},
    {"name": "Put/Call Ratio", "group": "Análise", "sections": [
      {"type": "text", "title": "Put/Call Ratio",
       "body": "Erro ao consultar: FileNotFoundError: cotahist.db not found at ..."}
    ]},
    {"name": "Volume por Strike", "group": "Análise", "sections": [
      {"type": "text", "title": "Volume por Strike",
       "body": "Erro ao consultar: FileNotFoundError: cotahist.db not found at ..."}
    ]}
  ]
}
```

---

*Last updated: 2026-08-18 (v1.0). See [CHANGELOG.md](CHANGELOG.md) for version history.*
