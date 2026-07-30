<- Back to [Report Overview](../REPORT.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(
    DISPATCH.get("report", {}),
    doc_sections=[...]
)
def report(
    action: str = "",
    trace_id: str = "",
    title: str = "",
    data: Any = None,
    config: dict = None,
    preset: str = "",
) -> dict:
    """..."""
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | **Yes** | Report type: `chart`, `map`, `report`, `dashboard`, `diagram`, `export`, `compare`, `timeline`, `scorecard`, `table`, `list`, `help` |
| `trace_id` | `str` | No | Trace ID for correlation. Auto-generated if empty. |
| `title` | `str` | No | Report title. Used in HTML `<title>` and header. |
| `data` | `Any` | No | Inline data (dict, list) or file path string. Use `data_path` in `config` for files. |
| `config` | `dict` | No | Action-specific configuration (see below). |
| `preset` | `str` | No | Pre-configured layout: `financial`, `code_audit`, `research`, `system_health`, `compare`, `timeline`, `scorecard`, `table` |

---

## ⚡ Config by Action

### `action="chart"`
```python
config = {
    "chart_type": "bar",        # bar | line | scatter | pie | radar | doughnut | polarArea
    "x_label": "",
    "y_label": "",
    "color": "",                # hex or "auto" for palette
    "data_path": "",            # local CSV/JSON/Excel path (SSRF-guarded)
    "theme": "dark",            # dark | light
}
```

### `action="map"`
```python
config = {
    "map_type": "markers",      # markers | heatmap | route | circles
    "center_lat": -15.78,
    "center_lon": -47.93,
    "zoom": 5,
    "theme": "dark",
}
```

### `action="report"`
```python
config = {
    "sections": [...],          # [{"title": "", "text": "", "type": "text|table|chart|mermaid|code"}]
    "kpis": [...],              # [{"label": "", "value": "", "delta": ""}]
    "sources": [...],           # [{"number": 1, "url": "", "title": "", "snippets": []}]
    "theme": "dark",
    "accent": "#0d9488",
}
```

### `action="dashboard"`
```python
config = {
    "tabs": [...],              # [{"name": "", "sections": [{"title": "", "text": "", "type": "..."}]}]
    "kpis": [...],
    "charts": [...],            # list of chart specs
    "columns": 2,               # 1-4
    "theme": "dark",
    "accent": "#0d9488",
}
# Each section `type` (v1.5): text | table | chart | mermaid | code | collapsible |
#                                  statement | ratio_grid | two_column | bug
#   - statement:  hierarchical rows with indent/subtotal/total styling (uses `statement_table` macro).
#                 Section shape: {"type":"statement", "rows":[{"label","value","indent"?,"is_subtotal"?,"is_total"?}]}
#   - ratio_grid: categorized KPI cards laid out in a responsive grid (uses `ratio_grid` macro).
#                 Section shape: {"type":"ratio_grid", "categories":[{"label","items":[{"label","value"}]}]}
#   - two_column: side-by-side balance-sheet layout (uses `two_column` macro).
#                 Section shape: {"type":"two_column", "left_title","left_rows", "right_title","right_rows"}
#   - financials_dashboard / valuation_dashboard adapters emit sections of these types automatically.

### `action="diagram"`
```python
config = {
    "diagram_type": "flowchart",  # flowchart | sequence | class | state | gantt
    "theme": "dark",
}
```

### `action="export"`
```python
config = {
    "format": "pdf",            # pdf | png | xlsx
    "width": 1920,              # pdf/png only
    "height": 1080,             # pdf/png only
    "adapter": "",              # xlsx only: flatten a skill result into table data
}
# pdf/png: data = path to an existing HTML report file
# xlsx:    data = table-shape dict | list of sections | skill result (with adapter) | .json path
```

### `action="compare"`
```python
config = {
    "before_label": "Before",
    "after_label": "After",
    "key_col": "",              # column to match rows by (for table mode)
    "theme": "dark",
}
```

### `action="timeline"`
```python
config = {
    "width": 900,
    "bar_height": 32,
    "row_gap": 48,
    "theme": "dark",
}
```

### `action="scorecard"`
```python
config = {
    "theme": "dark",
    "accent": "#0d9488",
}
```

### `action="table"`
```python
config = {
    "adapter": "",              # optional: flatten a skill result into table data
    "subtitle": "",             # optional subheading
    "theme": "dark",
    "accent": "#0d9488",
}
# data = {"sections":[...], "kpis":[...], "sources":[...]} (table shape)
#      OR a skill result dict (when config["adapter"] is set)
# Each section: {"title","columns"?, "rows","formats"?, "note"?}
#   rows: list-of-lists OR list-of-dicts (columns auto-derived from keys)
#   formats: {column_name: spec}  spec in brl|brl_full|pct|pct_raw|num|int|compact|text
```

### `action="list"`
```python
# No config needed. Returns catalog of all actions.
report(action="list")
```

### `action="help"`
```python
# data = action name to get help for
report(action="help", data="chart")
# data = empty -> returns help for all actions
report(action="help")
```

---

## 📋 Data Shapes

**Chart data:**
```python
# Single-series (backward-compatible)
data = {"x": ["Q1", "Q2", "Q3"], "y": [100, 150, 130]}
data = {"labels": ["A", "B"], "values": [30, 70]}  # pie/doughnut

# Multi-series (v1.2.2) — one line per dataset
data = {"x": ["1T25", "2T25", "3T25"],
        "datasets": [{"label": "Receita", "data": [100, 120, 130]},
                     {"label": "EBITDA", "data": [25, 30, 33]}]}

# Via adapter (flattens a skill result into multi-series chart data)
report(action="chart", title="PETR4 Trends",
       data=<financials JSON>, config={"chart_type":"line","adapter":"financials_quarterly_chart"})
```

**Map data:**
```python
data = {"lat": [-23.5, -22.9], "lon": [-46.6, -43.2], "labels": ["SP", "RJ"]}
data = [{"lat": -23.5, "lon": -46.6, "popup": "São Paulo", "color": "blue"}]
```

**Table data:**
```python
data = [{"Month": "Jul", "Sales": 400}, {"Month": "Aug", "Sales": 520}]
```

**Compare data:**
```python
data = {"before": {"price": 100, "volume": 500}, "after": {"price": 120, "volume": 500}}
# or table mode:
data = {"before": [{"ticker": "PETR4", "price": 30}], "after": [{"ticker": "PETR4", "price": 32}]}
```

**Timeline data:**
```python
data = [
    {"label": "Phase 1", "start": "2026-01-01", "end": "2026-02-15", "status": "done"},
    {"label": "Phase 2", "start": "2026-02-16", "end": "2026-04-01", "status": "active"},
]
```

**Scorecard data:**
```python
data = [
    {"name": "CPU", "score": 85, "target": 90, "weight": 1.0},
    {"name": "Memory", "score": 92, "target": 90, "weight": 1.0},
]
```

**Table data:**
```python
# Direct table shape
data = {
    "company": "PETR4",                          # optional, shown in header
    "sections": [
        {
            "title": "Quarterly Summary",
            "columns": ["Período", "Receita", "EBITDA", "Marg. EBITDA"],  # optional
            "rows": [                            # list-of-lists ...
                ["1T26", 100000, 25000, 0.25],
                ["4T25", 95000, 23000, 0.24],
            ],
            # ...OR list-of-dicts (columns auto-derived from keys):
            "rows": [{"Período":"1T26","Receita":100000,"EBITDA":25000,"Marg. EBITDA":0.25}],
            "formats": {"Receita": "brl", "EBITDA": "brl", "Marg. EBITDA": "pct"},
            "note": "Standalone quarters.",      # optional caption
        },
    ],
    "kpis": [{"label": "Receita", "value": 100000, "format": "brl"}],   # optional
    "sources": [{"title": "CVM DFP", "url": "..."}],                    # optional
}

# Adapter path — pipe a skill result straight in:
report(action="table", title="PETR4 Financials",
       data=<financials skill JSON>,
       config={"adapter": "financials_quarterly"})
```

---

## 🔌 Adapters (skill JSON → table data)

Adapters flatten a CVM/B3 skill result into the table data shape so the report
tool stays domain-agnostic. Set `config["adapter"]` on `table` or `export(xlsx)`.

| Adapter | Source skill (mode) | What it tables |
|---------|---------------------|----------------|
| `financials_quarterly` | `cvm/financials` quarterly | Wide table: periods × {Receita, EBITDA, Lucro, margins, ROE} + KPIs |
| `financials_annual` | `cvm/financials` annual | Same wide table, yearly + ROA/Payout |
| `financials_summary` | `cvm/financials` summary | KPIs + latest-annual detail (KV) + quarterly trend |
| `valuation_ratios` | `cvm/valuation` ratios | KPIs (Preço, P/L, P/VPA, EV/EBITDA, Div Yield, Mkt Cap) + full indicator table |
| `valuation_summary` | `cvm/valuation` summary | Ratios table + data-source availability table |
| `shareholders_shareholders` | `cvm/shareholders` shareholders | Named shareholders: %ON/%PN/%Total, qty, controlling |
| `shareholders_free_float` | `cvm/shareholders` free_float | Free float % + PF/PJ/inst counts per period |
| `shareholders_equity_structure` | `cvm/shareholders` equity_structure | Equity breakdown (BPP 2.03.*) per fiscal year |
| `shareholders_summary` | `cvm/shareholders` summary | Top shareholders + equity components (KV) |
| `dividends_history` | `cvm/dividends` history | B3 events: dates, rate, label (Dividendo/JCP) |
| `dividends_annual` | `cvm/dividends` annual | DVA 7.08.04.* totals (Dividendos, JCP, total) per year |
| `dividends_summary` | `cvm/dividends` summary | Recent events table + annual trend table |
| `comparison_side_by_side` | `cvm/comparison` side_by_side | 3 sections (valuation, financials, dividends), tickers as rows |
| `comparison_summary` | `cvm/comparison` summary | Single quick-compare table (10 KPIs) + KPI strip (P/L per ticker) |
| `comparison_growth` | `cvm/comparison` growth | Growth metrics table (QoQ + YoY + TTM ratios) |
| `financials_quarterly_chart` | `cvm/financials` quarterly | **Chart adapter** — multi-series line chart (Receita + EBITDA + Lucro Líquido over time) |
| `cotahist_close_chart` | `b3/cotahist` query | **Chart adapter** — daily close price line chart from COTAHIST |
| `cotahist_candlestick_chart` | `b3/cotahist` query | **Chart adapter** — OHLC candlestick chart from COTAHIST (needs chartjs-chart-financial plugin, auto-loaded) |
| `screener_sector` | `cvm/screener` sector | Peers table (sorted by P/L) + KPI strip (sector medians) |
| `financials_dashboard` (v1.5) | `cvm/financials` dashboard | **Dashboard adapter** — 5 tabs (Overview KPIs + DRE + Balanço + DFC + Ratios `ratio_grid`). Promotes top-level KPIs, converts statement tabs to `table` sections + ratios tab to `ratio_grid` |
| `valuation_dashboard` (v1.5) | `cvm/valuation` ratios/summary | **Dashboard adapter** — 5 themed tabs (Overview/Multiples/Profitability/Liquidity & Leverage/Efficiency & Growth) with 6 pre-formatted KPI cards. Uses `ratio_grid` sections for categorized ratios |
| `backtest_dashboard` (v1.6) | `cvm/backtest` dashboard | **Dashboard adapter** — 3 tabs (Overview with KPIs + equity curve, Trades table, Performance summary). Thin pass-through of `backtest.dashboard()` tab payload |
| `comparison_dashboard` (v1.6) | `cvm/comparison` dashboard | **Dashboard adapter** — 5 tabs (Overview/Valuation/Financials/Dividends/Growth). Thin pass-through of `comparison.dashboard()` tab payload |
| `dividends_dashboard` (v1.7) | `cvm/dividends` dashboard | **Dashboard adapter** — multi-tab (Overview + Events + Annual + Payable + Filings). Thin pass-through of `dividends.dashboard()` tab payload |
| `governance_dashboard` (v1.7) | `cvm/governance` dashboard | **Dashboard adapter** — multi-tab (Overview KPIs + Practices + By Chapter). Thin pass-through of `governance.dashboard()` tab payload |
| `historical_dashboard` (v1.7) | `cvm/historical` dashboard | **Dashboard adapter** — multi-tab (Overview + Ratios + Summary). Thin pass-through of `historical.dashboard()` tab payload |

Error / not_synced skill results render as a small status table (never crash).

---

## 🔢 Number Formatting (specs + Jinja filters)

Format specs are short string tags. A table column declares one spec in
`formats`; both the HTML template (via the `fmt` Jinja filter) and the xlsx
exporter (via `excel_format()`) honour it — one tag, two consistent renderings.

| Spec | HTML rendering | Excel number format | Use for |
|------|----------------|---------------------|---------|
| `brl` | R$ 1,23 B (compact) | `"R$ "#,##0.00` | Large BRL values (market cap, revenue) |
| `brl_full` | R$ 1.234,56 | `"R$ "#,##0.00` | Per-share BRL (price, EPS, DPA) |
| `pct` | 12,34% (from fraction 0.1234) | `0.00%` | Ratios computed as a/b (margins, ROE, yield) |
| `pct_raw` | 45,23% (from 45.23) | `0.00"%"` | CVM-stored % already in percent units (FRE ownership) |
| `num` | 1.234,56 | `#,##0.00` | Multiples (P/L, EV/EBITDA) |
| `int` | 1.234 | `#,##0` | Counts (shares, shareholders) |
| `compact` | 1,23 B | `#,##0.00` | Magnitude without currency |
| `text` | as-is | `@` | Labels, dates, strings (default) |

`None` / NaN always render as `—` in HTML and as an empty cell in xlsx.

**Jinja filters** (registered in `html.py`, usable in any template):

```jinja
{{ market_cap | brl }}              {# R$ 1,23 B #}
{{ roe | pct }}                      {# 18,50% (from 0.185) #}
{{ price | brl(false) }}            {# R$ 38,50 (full, no suffix) — 2nd arg = suffix #}
{{ shares | int }}                   {# 13.000.000.000 #}
{{ value | fmt("pct_raw") }}         {# dispatch by spec tag #}
{{ maybe_none | dash }}              {# — #}
```

---

## 🎨 Presets

Presets auto-configure layout, colors, and default sections.

| Preset | Use Case | Accent | Default Sections |
|--------|----------|--------|------------------|
| `financial` | B3/CVM market reports | `#0d9488` | overview, charts, data, sources |
| `code_audit` | Autocode bug reports | `#6366f1` | summary, issues, recommendations, changes, sources |
| `research` | Web research dossiers | `#3b82f6` | overview, findings, data, sources |
| `system_health` | Agent health dashboard | `#14b8a6` | overview, metrics, issues, logs |
| `compare` | Side-by-side diffs | `#0d9488` | diff |
| `timeline` | Project planning | `#3b82f6` | gantt, events |
| `scorecard` | Health/status checks | `#14b8a6` | overview, radar, details |
| `table` | Tabular statements (financials, ratios) | `#0d9488` | tables, sources |

---

## 🔒 Security

| Feature | Implementation |
|---------|---------------|
| **SSRF guard** | `data_path` blocks `http://`, `https://`, `ftp://`, `file://` unconditionally |
| **UNC guard** | Windows network paths (`\\server\share`, `//server/share`) blocked |
| **Path guard** | All paths resolved via `core.path_guard.resolve_path()` |
| **XSS prevention** | Jinja2 autoescape enabled; no `| safe` on user text; JSON `</script>`-escaped |
| **Atomic writes** | `_atomic_write` uses temp file + `os.replace` to prevent partial files |
| **trace_id sanitization** | Whitelist `a-zA-Z0-9_-` — no path traversal possible |
| **Playwright optional** | If not installed, returns graceful warning instead of crash |

### Template XSS Audit (v1.1)

| Template | Variable | Status |
|----------|----------|--------|
| `report.html` | `sec.text` | ✅ Auto-escaped (no `| safe`) |
| `dashboard.html` | `sec.text` | ✅ Auto-escaped (no `| safe`) |
| `diagram.html` | `mermaid_src` | ✅ Auto-escaped (no `| safe`) |
| `macros.html` | `content` (collapsible) | ✅ Auto-escaped (no `| safe`) |
| `map.html` | `map_config_json` | ✅ `| safe` kept (JSON in `<script>`) + `</script>` escaped |
| `scorecard.html` | `radar_config_json` | ✅ `| safe` kept (JSON in `<script>`) + `</script>` escaped |
| `timeline.html` | `svg_html` | ✅ `| safe` kept (builder-generated, `_escape_svg()` sanitizes text) |

### Mermaid Sanitization

| Check | Implementation |
|-------|---------------|
| Raw string input | `_sanitize_mermaid()` strips `<script>`, `<iframe>`, `<object>`, `<embed>`, event handlers (`onerror=`, `onclick=`), `javascript:` URLs |
| Dict-based input | `_dict_to_mermaid()` HTML-escapes all node labels and edge labels via `html.escape()` |
| Template render | `| safe` used on pre-sanitized string — Mermaid syntax characters (`>`, `|`, `[`, `]`) preserved |

### SVG Color Validation

| Check | Implementation |
|-------|---------------|
| User-provided color | `_validate_hex_color()` regex `^#[0-9a-fA-F]{6}$` |
| Invalid color | Falls back to `STATUS_COLORS[status]` |
| SVG text | `_escape_svg()` escapes `&`, `<`, `>`, `"` |

---

## 📤 Output

Returns:
```python
{
    "status": "success",
    "trace_id": "abc123",
    "type": "chart",
    "title": "Revenue",
    "html_path": "workspace/reports/abc123/Revenue.html",
    "chart_type": "bar",
}
```

A `manifest.json` is written alongside the HTML (for builders that support it):
```json
{
    "trace_id": "abc123",
    "action": "chart",
    "title": "Revenue",
    "created_at": "2026-06-26T21:00:00+0000",
    "files": ["Revenue.html"],
    "preset": "",
    "theme": "dark"
}
```

A `metrics.json` is also written for external ingestion:
```json
{
    "trace_id": "abc123",
    "action": "chart",
    "title": "Revenue",
    "created_at": "2026-06-26T21:00:00+0000",
    "files_count": 1,
    "preset": "",
    "theme": "dark",
    "accent": "",
    "chart_engine": "",
    "has_data": true
}
```

---

## 🧠 Memory Integration

Successful report generation stores an episodic memory entry:
```
"Generated chart report: 'Revenue' at workspace/reports/abc123/Revenue.html"
```

The memory hook is fire-and-forget — if storage fails, the report still returns successfully.

---

## 🖨️ Print / PDF / PNG / xlsx

- **Browser print** (`Ctrl+P`): Hides sidebar, expands all tabs/collapsible sections. Cards use `page-break-inside: avoid`.
- **Playwright export** (`action="export", format="pdf|png"`): Captures full report including hidden tabs. Requires `pip install playwright`.
- **xlsx export** (`action="export", format="xlsx"`): Writes table data to a multi-sheet `.xlsx` (native numeric cells, per-column Excel formats). Accepts table data, a skill result (`config["adapter"]`), or a `.json` path. Requires `pip install openpyxl`.
- **Fallback**: If Playwright/openpyxl is not installed, returns the available paths + a warning message.

---

*Last updated: 2026-07-29 (v1.7). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
