# 📊 Report Tool

The `report()` tool generates self-contained interactive HTML reports — charts, maps, dashboards, diagrams, comparisons, timelines, and scorecards. All outputs are saved to `workspace/reports/{trace_id}/` as portable HTML files that open in any browser without a server.

**Key characteristics:**
- **Atomic actions** — `chart`, `map`, `report`, `dashboard`, `diagram`, `export`, `compare`, `timeline`, `scorecard`, `table`, `list`, `help`. One action = one behavior
- **Auto-generated schema** — `@meta_tool` decorator builds `Literal` enum and docstring from DISPATCH
- **Lazy heavy imports** — pandas, jinja2, plotly, playwright, openpyxl imported inside function bodies only
- **Path guard integration** — All file operations validate through `core.path_guard`
- **Cancellation guard** — Aborts before any report generation if trace is cancelled
- **XSS-safe templates** — Jinja2 autoescape + no `| safe` on user-controlled text
- **Atomic file writes** — `_atomic_write` prevents partial/corrupted files on crash
- **Skill wiring (v1.2)** — `adapters/` adapters flatten CVM/B3 skill JSON into the `table` action (and `export` xlsx) via `config["adapter"]`. The report tool stays domain-agnostic; number formatting (BRL/%) is shared between HTML and xlsx via one spec vocabulary in `formats.py`.

---

## 🚀 Quick Start

```python
# Generate a bar chart
report(action="chart", title="Revenue", data={"x": ["Q1", "Q2"], "y": [100, 150]})

# Generate a multi-section report
report(action="report", title="Analysis", config={"sections": [{"title": "Summary", "text": "...", "type": "text"}]})

# Render financial statements as a table (v1.2)
report(action="table", title="PETR4 Financials",
       data=<financials skill JSON>, config={"adapter": "financials_quarterly"})

# Export a skill result to Excel (v1.2)
report(action="export", title="PETR4 Valuation",
       data=<valuation skill JSON>, config={"format": "xlsx", "adapter": "valuation_ratios"})

# List all available actions
report(action="list")
```

---

## 🔄 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Bar/line/pie chart | `report(chart)` | Chart.js, client-side, no server |
| Interactive map | `report(map)` | Leaflet.js, OpenStreetMap tiles |
| Multi-section report | `report(report)` | Single-scroll, KPIs, tables, sources |
| Tabbed dashboard | `report(dashboard)` | Multi-panel with side nav |
| Architecture diagram | `report(diagram)` | Mermaid.js, auto-rendered |
| Side-by-side diff | `report(compare)` | Delta highlighting, dict/table/list modes |
| Project timeline | `report(timeline)` | SVG Gantt, status colors, today marker |
| Health/status scorecard | `report(scorecard)` | RAG colors, radar chart, weighted scoring |
| Tabular statements | `report(table)` | Financial statements / ratio tables, per-column BRL/%, search filter |
| Export to PDF/PNG | `report(export)` | Playwright headless capture |
| Export to xlsx | `report(export)` | Multi-sheet Excel, native numeric cells, skill adapter support |
| List available actions | `report(list)` | Self-discovery for LLMs |
| Get action help | `report(help)` | Metadata: params, config keys, examples |

---

## ⚙️ Configuration

- **Playwright** (optional): `pip install playwright` — required for PDF/PNG export
- **openpyxl** (optional): `pip install openpyxl` — required for xlsx export
- **Templates**: Jinja2 autoescape enabled; all template-specific JS loaded in `{% block scripts %}`
- **Number formatting**: shared spec vocabulary (`brl`, `pct`, `num`, …) in `formats.py` — used by the `fmt` Jinja filter (HTML) and `excel_format()` (xlsx)
- **Adapters**: 12 skill→table adapters in `adapters/`; invoked via `config["adapter"]` on `table`/`export(xlsx)`
- **Output root**: `workspace/reports/{trace_id}/` (resolved via `core.path_guard`)

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [Architecture](report/ARCHITECTURE.md) | File maps, design decisions, test trees, mermaid diagrams |
| [API Reference](report/API.md) | Tool signature, actions, config, data shapes, adapters, formatting, security, output |
| [Changelog](report/CHANGELOG.md) | Version history (v1.2 skill wiring), breaking changes, roadmap |
| [Instructions](report/INSTRUCTIONS.md) | AI editing rules, NEVER DO, ALWAYS DO, anti-patterns |

---

*Architecture: thin facade + @meta_tool + atomic action modules + auto-discovery + lazy imports + XSS-safe templates + atomic file writes + (v1.2) transforms adapters + shared number-format specs.*
