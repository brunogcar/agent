<- Back to [Report Overview](../REPORT.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.2.6 | 2026-07-25 | **Candlestick chart + screener financials.** (1) New cotahist_candlestick_chart adapter — OHLC candlestick chart from COTAHIST using chartjs-chart-financial plugin. charts.py detects _candlestick shape, chart.html loads financial plugin CDN conditionally. (2) screener_sector adapter enriched with 7 new columns (Receita, EBITDA, Lucro, Marg. EBITDA, Marg. Liquida, Cresc. Receita, Payout). Total 19 adapters. |
| v1.2.5 | 2026-07-25 | **Screener adapter.** New screener_sector adapter for the new cvm/screener skill. Peers table sorted by P/L cheapest-first + KPI strip with sector medians. Total 18 adapters. |
| v1.2.4 | 2026-07-25 | **COTAHIST adapter fix.** v1.2.3 cotahist_close_chart accepted ticker strings, but apply_adapter() requires dicts (all adapters receive dicts). Removed the string path — adapter now accepts COTAHIST query result dicts only. Use the 2-step pattern: query COTAHIST first, then pipe result to chart. |
| v1.2.3 | 2026-07-25 | **COTAHIST chart adapter.** New cotahist_close_chart adapter — line chart of daily close price from COTAHIST. Accepts a COTAHIST query result OR a ticker string (queries internally). Total 17 adapters. |
| v1.2.2 | 2026-07-25 | **Multi-series charts + growth/chart adapters.** (1) `charts._to_chartjs_config` now supports multi-series data `{"x":[], "datasets":[{"label","data"},...]}` — backward-compatible with single-series. (2) New `financials_quarterly_chart` adapter — multi-series trend chart (Receita + EBITDA + Lucro Líquido). (3) New `comparison_growth` adapter. (4) Chart action + builder now support `config["adapter"]`. Total 16 adapters. |
| v1.2.1 | 2026-07-25 | **Comparison skill adapters.** Added `comparison_side_by_side` + `comparison_summary` adapters (2 new, total 14) for the new `cvm/comparison` skill. Updated `report.py` docstring adapter list + API.md adapter table. |
| v1.2 | 2026-07-25 | **Skill wiring: table action + adapter layer + number formatting + xlsx export.** New `table` action for financial statements/ratio tables. New `adapters/` package (12 adapters) flattening CVM/B3 skill JSON → table data. New `formats.py` (BRL/%/compact) registered as Jinja filters + reused by xlsx. `export` now supports `format:"xlsx"` (openpyxl, multi-sheet, native numeric cells). New `table` preset. `report.py` docstring now lists adapters. See v1.2 detail below. |
| v1.1 | 2026-07-03 | Security hardening + template fixes (`\| safe` audit, atomic writes, UNC block, `@register_action` dedup, Chart.js dedup, cancellation import fix). |
| v1.0 | 2026-06-26 | Initial 11-action report tool with `@meta_tool` + `@register_action` auto-discovery. |

---

## 🆕 v1.2 — Skill Wiring (table + adapters + formats + xlsx)

Wires the CVM/B3 analytical skills to the report tool so the LLM can render and
export financial statements in one call. Driven by a collective LLM review
(OpenAI, Claude, Mimo, DeepSeek, Mistral, Qwen) that converged on four needs:
financial statements are **tables**; skill JSON must be **flattened** by an
adapter (not coupled into the report tool); numbers need **BRL/% formatting**;
and statements need **xlsx export**.

### Phase 1 — `table` action
- New action `report(action="table", ...)` renders one or more tables with
  per-column number formatting, sticky headers, per-table search filter, and a
  sidebar section switcher.
- Data shape: `{"sections":[{title, columns, rows, formats, note}], "kpis":[...], "sources":[...]}`.
  Rows accept list-of-lists **or** list-of-dicts (columns auto-derived).
- Template `templates/table.html` (extends `base.html`); builder `table.py`;
  action wrapper `actions/table.py` (auto-discovered).
- Registered in `DISPATCH_METADATA["table"]` + `PRESETS["table"]`.

### Phase 2 — `adapters/` adapter layer
- New package `tools/report_ops/adapters/` with 12 adapters registered via
  `@register_adapter(name)`: `financials_{quarterly,annual,summary}`,
  `valuation_{ratios,summary}`, `shareholders_{shareholders,free_float,equity_structure,summary}`,
  `dividends_{history,annual,summary}`.
- Each adapter is a pure function `skill_result -> table_data`. The report tool
  stays domain-agnostic: it never imports CVM/B3 code. Skills don't change.
- Invoked via `config["adapter"]` on both `table` and `export` actions — the LLM
  pipes a skill JSON straight in: `report(action="table", data=<skill JSON>,
  config={"adapter":"financials_quarterly"})`.
- Error/no-data skill results render as a small status table instead of crashing.

### Phase 3 — Number formatting (`formats.py` + Jinja filters)
- New `tools/report_ops/formats.py` with spec tags: `brl` (compact R$ 1,23 B),
  `brl_full` (R$ 1.234,56), `pct` (fraction→12,34%), `pct_raw` (already-%),
  `num`, `int`, `compact`, `text`. Reuses `core.br_validator.format_brl`.
- Registered as Jinja filters on the singleton env: `brl`, `pct`, `num`, `int`,
  `compact`, `dash`, and `fmt(value, spec)` (dispatch by tag). Usable in any
  template (`{{ x | brl }}`, `{{ m | pct }}`).
- None/NaN always render as `—` in HTML (empty cell in xlsx) — never `"None"`.
- `excel_format(spec)` + `is_numeric_spec(spec)` bridge the same spec tags to
  native Excel number formats, so HTML and xlsx render identically.

### Phase 4 — xlsx export
- `export` action now accepts `config["format"]="xlsx"`: writes a multi-sheet
  `.xlsx` from table data (or a skill result via `config["adapter"]`, or a
  `.json` file path).
- Each section → one sheet (name sanitized to Excel rules, ≤31 chars, deduped).
  Header row frozen + styled. **Numeric cells stay native** with Excel number
  formats (`0.00%`, `"R$ "#,##0.00`, …) so they remain sortable/summable.
- openpyxl imported lazily; graceful warning if not installed (mirrors the
  Playwright optional-dep pattern).
- pdf/png path unchanged — `run()` branches on `format` before touching libs.

### Files added
- `tools/report_ops/formats.py`
- `tools/report_ops/table.py`
- `tools/report_ops/actions/table.py`
- `tools/report_ops/templates/table.html`
- `tools/report_ops/adapters/__init__.py` (registry + helpers)
- `tools/report_ops/adapters/financials.py`
- `tools/report_ops/adapters/valuation.py`
- `tools/report_ops/adapters/shareholders.py`
- `tools/report_ops/adapters/dividends.py`

### Files changed
- `tools/report_ops/html.py` — register Jinja filters in `_get_env()`.
- `tools/report_ops/export.py` — added `_export_xlsx()` + `_coerce_xlsx_data()`;
  `run()` now branches on `format`.
- `tools/report_ops/_registry.py` — `table` in `DISPATCH_METADATA` + `PRESETS`;
  `export` config_keys gained `adapter`.
- `tools/report_ops/actions/export.py` — help text + examples for xlsx/adapter.
- `tools/report.py` — `doc_sections` now lists `table`, adapters, xlsx example,
  and the `table` preset.

---

## ⚠️ Breaking Changes (v1 → v1.1)

| Old | New | Migration |
|-----|-----|-----------|
| Manual `DISPATCH` dict with `_dispatch_*` wrappers | `@register_action` auto-discovery | No migration needed — same API |
| Manual docstring in `report()` | `@meta_tool` auto-generated | No migration needed — same API |
| `chart` rendered via `report.html` template | Dedicated `chart.html` template | No migration — output is identical |
| `sec.text | safe` in templates | Auto-escaped (no `| safe`) | No migration — safer by default |
| `mermaid_src | safe` in diagram template | Auto-escaped with pre-sanitization | Mermaid.js parses escaped text correctly |
| `export` resolved against `agent` root | Resolved against `workspace` root | Reports now scoped to workspace |
| No UNC path blocking | UNC paths (`\\server\share`) blocked | Already handled by path guard |
| Cancellation import inside try/except | Import moved outside try block | ImportError no longer masked as "cancelled" |

### v1.1 (security hardening + template fixes)

- Removed `| safe` from all user-controlled template variables (`sec.text`, `mermaid_src`, `content`)
- Added `.replace("</", "<\/")` to all JSON dumps before template render (prevents `</script>` injection)
- Added `_sanitize_mermaid()` in `diagrams.py` — strips `<script>`, `<iframe>`, `<object>`, `<embed>`, event handlers, `javascript:` URLs from raw mermaid strings
- Added `_validate_hex_color()` in `timeline.py` — regex `^#[0-9a-fA-F]{6}$`, fallback to `STATUS_COLORS`
- Added `_escape_svg()` quote escaping (`"` → `&quot;`) in `timeline.py`
- Added UNC path block in `data.py`: `if lowered.startswith(("\\\\", "//"))`
- Changed `export.py` to use `resolve_path(..., default_root="workspace")`
- Added `_atomic_write` to `html.py` (temp file + `os.replace`)
- Added `report.list` and `report.help` actions for LLM self-discovery
- Added `elapsed_ms` timing to all report results
- Added `tracer.warning()` logging for memory hook failures
- Added duplicate action guard in `@register_action`: raises `ValueError` on collision
- Fixed `report.html` and `dashboard.html`: added `{% extends "base.html" %}` + `{% block content %}` + `{% block scripts %}`
- Fixed `dashboard.html` data structure: outer `for tab in tabs` → inner `for sec in tab.sections`
- Removed Chart.js from `base.html` `<head>` — loaded by individual templates (`chart.html`, `scorecard.html`) to avoid double-load

---

## 🔧 Bugs Found & Fixed During v1.1 Review

These were caught by multi-LLM review (Gemini, DeepSeek, Mistral, Qwen, GLM, mimo, Claude) and fixed in v1.1. Future editors should verify these patterns are preserved.

### Template `extends` Missing
**Bug:** `report.html` and `dashboard.html` had no `{% extends "base.html" %}` — produced raw HTML fragments without CSS/layout.  
**Fix:** Added `{% extends "base.html" %}` + `{% block sidebar %}` + `{% block content %}` + `{% block scripts %}` to both templates.  
**Lesson:** Always verify templates render standalone, not just as fragments inside other templates.

### Dashboard Data Structure Mismatch
**Bug:** `dashboard.html` iterated `tabs` as flat sections (`for sec in tabs`), but builder passed `tabs=[{"name": "Tab1", "sections": [...]}]`. Template expected `sec.title`, builder provided `tab.name` + `tab.sections`.  
**Fix:** Restructured to outer `for tab in tabs` → inner `for sec in tab.sections`.  
**Lesson:** Template variable names must match builder data structures exactly.

### Mermaid Autoescape Breaks Syntax
**Bug:** Removing `| safe` from `mermaid_src` caused Jinja2 autoescape to convert `>` → `&gt;`, breaking Mermaid.js syntax (`A --> B` became `A --&gt; B`).  
**Fix:** Added `| safe` back to `mermaid_src` in `diagram.html`, but added `_sanitize_mermaid()` in `diagrams.py` to strip HTML tags/event handlers before template render. Dict-based diagrams use `html.escape()` on labels.  
**Lesson:** `| safe` is required for syntax-heavy strings, but MUST be paired with pre-sanitization.

### SVG Color Injection
**Bug:** `timeline.py` injected `ev["color"]` directly into SVG `fill` attribute. Invalid hex or malicious strings broke SVG syntax.  
**Fix:** Added `_validate_hex_color()` with regex `^#[0-9a-fA-F]{6}$`. Fallback to `STATUS_COLORS[status]`.  
**Lesson:** Never inject user data into HTML/SVG attributes without validation.

### Cancellation Import Masks ImportError
**Bug:** `from core.runtime.cancellation import ensure_not_cancelled` was inside `try/except BaseException`. If module missing, `ImportError` (a `BaseException`) was caught and reported as "Workflow cancelled."  
**Fix:** Moved import outside try block. Set `ensure_not_cancelled = None` if `ImportError`, skip cancellation check.  
**Lesson:** Never put imports inside `except BaseException` — it masks real errors.

### Chart.js Double-Loaded
**Bug:** `base.html` loaded Chart.js CDN in `<head>`. `chart.html` and `scorecard.html` also loaded it. Double load wasted bandwidth and risked initialization conflicts.  
**Fix:** Removed Chart.js from `base.html`. Added `{% block scripts %}` at end of body. Individual templates load Chart.js in their script block.  
**Lesson:** Shared base templates should not load library-specific scripts — let leaf templates handle it.

### Raw String Escape Bugs
**Bug:** Regex patterns in `_sanitize_mermaid()` used raw strings with unescaped quotes: `r"[^\s>'"]+"` caused `SyntaxError: unterminated string literal`.  
**Fix:** Properly escaped inner quotes: `r"[^\s>\"']+"`.  
**Lesson:** Always `compileall` before `pytest` — syntax errors in new code crash with confusing tracebacks.

### Template Test Data Structure Mismatch
**Bug:** Tests for `dashboard.html` passed `tabs=[{"title": "Tab1", "text": payload}]` but template expected `tabs=[{"name": "Tab1", "sections": [{"title": "Sec", "text": payload}]}]`. Tests passed empty content, assertions on escaped text failed.  
**Fix:** Updated all test data to match new template structure.  
**Lesson:** When refactoring templates, update ALL tests that render those templates — not just the builder tests.

---

## ✅ Completed

| Feature | Status | Notes |
|--------|--------|-------|
| `comparison_side_by_side` / `comparison_summary` adapters | ✅ v1.2.1 | 2 new adapters for `cvm/comparison` skill (total 14) |
| `table` action | ✅ v1.2 | Multi-table statements, per-column number formatting, search filter |
| `adapters/` adapter layer | ✅ v1.2 | 12 adapters flatten CVM/B3 skill JSON → table data (domain-agnostic report tool) |
| Number formatting (`formats.py`) | ✅ v1.2 | BRL/%/compact specs as Jinja filters + Excel number formats |
| xlsx export | ✅ v1.2 | `export(format="xlsx")` multi-sheet, native numeric cells (openpyxl, lazy) |
| `table` preset | ✅ v1.2 | Theme/accent defaults for tabular reports |
| `compare` | ✅ v1.1 | Side-by-side diff with delta highlighting |
| `timeline` | ✅ v1.1 | SVG Gantt chart with status colors |
| `scorecard` | ✅ v1.1 | RAG dashboard with radar chart |
| `list` | ✅ v1.1 | Self-discovery: all actions with metadata |
| `help` | ✅ v1.1 | Per-action metadata lookup |
| `@meta_tool` refactor | ✅ v1.1 | Auto-generated schema + docstring |
| `@register_action` pattern | ✅ v1.1 | Auto-discovery via `actions/` directory |
| `chart.html` template | ✅ v1.1 | Dedicated template for Chart.js |
| XSS `| safe` removal | ✅ v1.1 | All user text auto-escaped |
| `_atomic_write` | ✅ v1.1 | Temp file + `os.replace` |
| UNC path blocking | ✅ v1.1 | `\\server\share` blocked |
| Export workspace scoping | ✅ v1.1 | `default_root="workspace"` |
| Template standalone rendering | ✅ v1.1 | Fixed missing `{% extends %}` in report.html, dashboard.html |
| Mermaid pre-sanitization | ✅ v1.1 | `_sanitize_mermaid()` strips HTML tags, event handlers, javascript: URLs |
| SVG color validation | ✅ v1.1 | `_validate_hex_color()` regex + fallback |
| Cancellation import fix | ✅ v1.1 | Import outside try block |
| Chart.js deduplication | ✅ v1.1 | Removed from base.html, loaded per-template |
| `elapsed_ms` timing | ✅ v1.1 | Added to all report results |
| Memory hook logging | ✅ v1.1 | `tracer.warning()` on failure |
| Duplicate action guard | ✅ v1.1 | `ValueError` on collision in `@register_action` |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Chart presets for skills | `financials_quarterly_chart` adapter (revenue/EBITDA trend line) | v1.3 |
| Candlestick chart for COTAHIST | OHLCV adapter → `chart` action (Candlestick.js or Chart.js finance) | v1.3 |
| `compose` multi-action | One call → table + chart + KPIs in a single dashboard | v2 |
| Adapter registry self-doc | `report(action="help", data="adapters")` lists adapters + source skills | v1.3 |
| Per-action preset override | Action-level preset merging (currently global only) | v2 |
| Conditional registration | Hide `export` pdf/png if Playwright missing; xlsx if openpyxl missing | v2 |
| `report.preview` | Low-res preview before full render | v3 |
| Template hot-reload | Dev mode: auto-reload templates on change | v3 |
| Theme system expansion | Custom themes beyond dark/light | v3 |
| investsite adapters | `investsite_indicators`, `investsite_statements` adapters | v1.3 |
| Cross-company comparison adapter | Multi-ticker table (P/L, ROE side-by-side) | v1.4 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | `search_files` not yet implemented for reports | No FTS index exists | Skip |
| 2 | `chart_engine: "plotly"` config key | Chart.js is the only implemented engine | Skip |
| 3 | `export` PNG format | Works but PDF is primary use case | Skip |
| 4 | Very large datasets (>10K points) | May slow Chart.js rendering in browser | Skip |
| 5 | Mermaid.js offline bundle | Requires internet connection for CDN | Skip |

---

*Last updated: 2026-07-25 (v1.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
