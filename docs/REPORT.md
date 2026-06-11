# Report Tool Documentation

## Overview

The `report()` tool generates self-contained HTML dashboards, charts, maps, and diagrams. All outputs are saved to `workspace/reports/{trace_id}/` as portable HTML files that open in any browser without a server.

## Architecture

```
tools/report.py              # @tool facade — dispatcher, trace_id, contracts
tools/report_core/           # Engine package
  _registry.py               # DISPATCH {chart, map, report, dashboard, diagram, export}
  contracts.py               # report_ok / report_fail with trace_id injection
  paths.py                   # Per-run folder resolver
  data.py                    # CSV/JSON/Excel/SQLite loader with SSRF guard
  charts.py                  # Chart.js primary (Plotly optional)
  maps.py                    # Leaflet.js maps
  diagrams.py                # Mermaid.js diagrams
  html.py                    # Jinja2 renderer (thread-safe)
  export.py                  # Playwright PDF/PNG (lazy import, optional)
  templates/                 # Jinja2 templates
    base.html                # Layout + sidebar + topbar + theme toggle
    macros.html              # Reusable components
    dashboard.html           # Multi-panel grid
    report.html              # Single-scroll
    map.html                 # Full-screen map
    diagram.html             # Mermaid architecture
```

## Tool Signature

```python
report(
    action:   str,           # chart | map | report | dashboard | diagram | export
    trace_id: str = "",     # auto-generated if empty
    title:    str = "",
    data:     Any = None,   # inline dict/list or None (use data_path)
    config:   dict = None,  # action-specific options
    preset:   str = "",     # financial | code_audit | research | system_health
) -> dict
```

### Core Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | Yes | Report type: `chart`, `map`, `report`, `dashboard`, `diagram`, `export` |
| `trace_id` | `str` | No | Trace ID for correlation. Auto-generated if empty. |
| `title` | `str` | No | Report title. Used in HTML `<title>` and header. |
| `data` | `Any` | No | Inline data (dict, list). Use `data_path` inside `config` for files. |
| `config` | `dict` | No | Action-specific configuration (see below). |
| `preset` | `str` | No | Pre-configured layout: `financial`, `code_audit`, `research`, `system_health` |

### Config by Action

#### `action="chart"`
```python
config = {
    "chart_type": "bar",      # bar | line | scatter | pie | radar | doughnut | polarArea
    "chart_engine": "chartjs", # chartjs (default) | plotly
    "x_label": "",
    "y_label": "",
    "color": "",              # hex or "auto" for palette
    "data_path": "",          # local CSV/JSON/Excel path (SSRF-guarded)
    "x_col": "",
    "y_col": "",
    "label_col": "",
    "theme": "dark",          # dark | light
    "export_png": False,
    "export_pdf": False,
}
```

#### `action="map"`
```python
config = {
    "map_type": "markers",    # markers | heatmap | route | circles
    "center_lat": -15.78,
    "center_lon": -47.93,
    "zoom": 5,
    "theme": "dark",
}
```

#### `action="dashboard"`
```python
config = {
    "sections": [...],        # list of section dicts
    "kpis": [...],            # [{"label": "", "value": "", "delta": ""}]
    "charts": [...],          # list of chart specs
    "tabs": [...],            # top-level tabs
    "columns": 2,             # 1-4
    "theme": "dark",
    "accent": "#0d9488",
    "export_png": False,
    "export_pdf": False,
}
```

#### `action="report"`
```python
config = {
    "sections": [...],        # [{"title": "", "text": "", "type": "text|table|chart"}]
    "kpis": [...],
    "sources": [...],         # [{"number": 1, "url": "", "title": "", "snippets": []}]
    "theme": "dark",
    "accent": "#0d9488",
    "export_pdf": False,
}
```

#### `action="diagram"`
```python
config = {
    "diagram_type": "flowchart",  # flowchart | sequence | class | state | gantt
    "mermaid_code": "",           # raw Mermaid syntax
    "theme": "dark",
}
```

#### `action="export"`
```python
config = {
    "html_path": "",          # path to existing HTML report
    "formats": ["pdf", "png"], # pdf | png
}
```

### Data Shapes

**Chart data:**
```python
data = {"x": ["Q1", "Q2", "Q3"], "y": [100, 150, 130]}
data = {"labels": ["A", "B"], "values": [30, 70], "hole": 0.3}  # pie
data = {"z": [[1,2],[3,4]], "x": ["a","b"], "y": ["c","d"]}   # heatmap
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

## Presets

Presets auto-configure layout, colors, and default sections.

| Preset | Use Case | Accent | Default Sections |
|--------|----------|--------|------------------|
| `financial` | B3/CVM market reports | `#0d9488` | KPIs, charts, data tables, sources |
| `code_audit` | Autocode bug reports | `#6366f1` | Issues, recommendations, changes, sources |
| `research` | Web research dossiers | `#3b82f6` | Overview, findings, data, sources |
| `system_health` | Agent health dashboard | `#14b8a6` | Radar chart, metrics, status cards |

## Security

- `data_path` accepts **local filesystem paths only**. `http://` and `https://` are **hard blocked**.
- All paths resolved via `core.path_guard.resolve_path()`.
- `workspace/reports/{trace_id}/` is the only write target.
- Playwright (PDF export) is an **optional** dependency. If absent, HTML-only output with a warning.

## Output

Returns:
```python
{
    "status": "success",
    "trace_id": "abc123",
    "action": "dashboard",
    "title": "Q3 Analysis",
    "html_path": "workspace/reports/abc123/Q3_Analysis.html",
    "files": ["Q3_Analysis.html"],  # + .pdf / .png if exported
}
```

A `manifest.json` is also written alongside the HTML:
```json
{
  "trace_id": "abc123",
  "action": "dashboard",
  "title": "Q3 Analysis",
  "created_at": "2026-06-11T14:23:00+00:00",
  "files": ["Q3_Analysis.html"],
  "preset": "financial",
  "theme": "dark"
}
```

## Memory Integration

Successful report generation stores an episodic memory entry:
```
"Generated dashboard report: 'Q3 Analysis' at workspace/reports/abc123/Q3_Analysis.html"
```

## Keyboard Shortcuts

When viewing a report in the browser:
- `j` / `k` — cycle sidebar navigation
- `Escape` — jump to first section (summary/overview)

## CDN Fallback

If Chart.js fails to load, the report displays a raw data table fallback.

## Print / PDF

- `Ctrl+P` (or the print button) hides the sidebar and expands all tabs/collapsible sections.
- Cards use `page-break-inside: avoid` to prevent splitting across pages.
- Playwright export (`action="export"`) captures the full report including hidden tabs.

## Testing

Run report tests:
```bash
cd D:\mcp\agent
D:\mcp\agent\venv\Scripts\python.exe -m pytest tests/tools/report/ -v
```

## Future

- Phase 3: `compare`, `timeline`, `scorecard` actions
- Phase 4: Workflow auto-report (understand, research, autocode)
- Phase 5: Grafana metrics ingestion, gateway static route