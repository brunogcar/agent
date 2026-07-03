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
| `action` | `str` | **Yes** | Report type: `chart`, `map`, `report`, `dashboard`, `diagram`, `export`, `compare`, `timeline`, `scorecard`, `list`, `help` |
| `trace_id` | `str` | No | Trace ID for correlation. Auto-generated if empty. |
| `title` | `str` | No | Report title. Used in HTML `<title>` and header. |
| `data` | `Any` | No | Inline data (dict, list) or file path string. Use `data_path` in `config` for files. |
| `config` | `dict` | No | Action-specific configuration (see below). |
| `preset` | `str` | No | Pre-configured layout: `financial`, `code_audit`, `research`, `system_health`, `compare`, `timeline`, `scorecard` |

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
    "tabs": [...],              # [{"title": "", "text": "", "type": "..."}]
    "kpis": [...],
    "charts": [...],            # list of chart specs
    "columns": 2,               # 1-4
    "theme": "dark",
    "accent": "#0d9488",
}
```

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
    "format": "pdf",            # pdf | png
    "width": 1920,
    "height": 1080,
}
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
data = {"x": ["Q1", "Q2", "Q3"], "y": [100, 150, 130]}
data = {"labels": ["A", "B"], "values": [30, 70]}  # pie/doughnut
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

## 🖨️ Print / PDF / PNG

- **Browser print** (`Ctrl+P`): Hides sidebar, expands all tabs/collapsible sections. Cards use `page-break-inside: avoid`.
- **Playwright export** (`action="export"`): Captures full report including hidden tabs. Requires `pip install playwright`.
- **Fallback**: If Playwright is not installed, returns HTML path + warning message.

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
