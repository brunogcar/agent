<- Back to [Report Overview](../REPORT.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

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
| Action-level presets | Per-action override of global presets | v2 |
| Action-level timing | `elapsed_ms` in results | v2 |
| Conditional registration | Hide `export` if Playwright missing | v2 |
| `report.compose` | Multi-step reports in one call | v3 |
| `report.preview` | Low-res preview before full render | v3 |
| Template hot-reload | Dev mode: auto-reload templates on change | v3 |
| Theme system expansion | Custom themes beyond dark/light | v3 |

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

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
