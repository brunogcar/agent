<- Back to [Report Overview](../REPORT.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add subcommand parsing to action handlers** — one action = one behavior.
2. **Never import pandas/jinja2/plotly/playwright at module level in `actions/`** — lazy imports only. Use `from tools.report_ops import charts` inside the function body.
3. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks. Internal dispatch wrappers can use `**kwargs`.
4. **Never print to stdout** — MCP stdio corruption. Use `sys.stderr` if needed.
5. **Never create `.bak` files** — forbidden by project rules.
6. **Never use `| safe` in templates for user-controlled text** — XSS vector. Jinja2 autoescape handles it. Exception: syntax-heavy strings (Mermaid, JSON) that are pre-sanitized.
7. **Never touch `@meta_tool` or `@register_action` shared decorators** — use `help_text` for param docs. Infrastructure changes need separate commits.
8. **Never put non-action files in `report_ops/actions/`** — auto-discovery imports everything.
9. **Never cache `cfg.workspace_root` at module level** — breaks test mocking.
10. **Never skip `compileall` before `pytest`** — syntax errors crash with confusing tracebacks.
11. **Never rewrite entire files when surgical edits suffice** — preserve existing code.
12. **Never forget `</script>` escaping on JSON dumps** — `json.dumps(obj).replace("</", "<\/")`
13. **Never register actions outside the `report` namespace** — `DISPATCH["report"]` is the only valid key.
14. **Never put imports inside `except BaseException`** — masks real errors (e.g., `ImportError` reported as "cancelled").
15. **Never inject user data into HTML/SVG attributes without validation** — always sanitize/validate before template render.
16. **Never load library-specific scripts in `base.html`** — let leaf templates load their own JS in `{% block scripts %}`.
17. **Never import CVM/B3/skill code from `report_ops/`** — the report tool is domain-agnostic. Skill JSON is flattened by `adapters/` adapters only. Coupling here defeats the v1.2 layering.
18. **Never pre-format numbers into strings inside builders/adapters for multi-period tables** — emit raw numbers + a per-column spec (`brl`/`pct`/…). The `fmt` Jinja filter (HTML) and `excel_format()` (xlsx) render them. Pre-formatting breaks native Excel cells. Exception: key-value indicator tables (`_kv_section`) where each row has its own unit.
19. **Never register an adapter name that doesn't match `<skill>_<mode>`** — naming convention is how the LLM guesses adapter names without `report(action="help")`.
20. **Never put adapter modules outside `tools/report_ops/adapters/`** — `adapters/__init__.py` imports the four known modules to trigger `@register_adapter`. New adapter files must be added there.

## ✅ ALWAYS DO

17. **Always verify templates render standalone** — `{% extends %}` + `{% block %}` structure must be complete.
18. **Always match template variable names to builder data structures** — `tab.name` vs `sec.title`, `tab.sections` vs flat `tabs`.
19. **Always pair `| safe` with pre-sanitization** — if you need `| safe` for syntax, sanitize the string first.
20. **Always update tests when refactoring templates** — test data structures must match template expectations.
21. **Always add `{% block scripts %}` for template-specific JS** — Chart.js, Mermaid init, etc.
22. **Always use `compileall` before `pytest`** — catches syntax errors early.
23. **Always reuse `core.br_validator.format_brl` in `formats.py`** — don't hand-roll BRL formatting; the BR stack already has a tested implementation.
24. **Always render `None`/NaN as `—` (HTML) / empty cell (xlsx)** — use `formats._is_missing()`; never let `"None"` leak into a report.
25. **Always make adapters defensive** — a skill `not_found`/`not_synced` result must render a small status table via `_error_table()`, not raise. The LLM should see the cause inline.
26. **Always honour `config["adapter"]` in both `table` and `export(xlsx)`** — one adapter name must work for both render paths so the LLM's mental model stays simple.

---

## 🚫 Anti-Patterns & Lessons Learned

### v1.2 — Adapter layer separation
> - **What happened:** Temptation to let `table.py` import `skills.cvm.financials` directly and "just know" the JSON shape.
> - **Why it matters:** Couples the report tool to every skill's output format. Adding/changing a skill would require report-tool edits; report-tool changes risk breaking skills.
> - **Fix:** All skill knowledge lives in `adapters/` adapters registered via `@register_adapter`. `table.py` and `export.py` only know `config["adapter"]` → `apply_adapter(name, data)`. The report tool imports zero CVM/B3 modules.

### v1.2 — One spec tag, two renderings
> - **What happened:** Formatting BRL/percent in HTML with one function and again differently in xlsx risks divergence (e.g. HTML shows "R$ 1,23 B" but Excel shows "1.23B").
> - **Why it matters:** Inconsistent formatting erodes trust in exports; re-implementing BRL formatting per renderer duplicates `core.br_validator` logic.
> - **Fix:** A single spec vocabulary in `formats.py`. `apply_fmt(value, spec)` for HTML (Jinja `fmt` filter), `excel_format(spec)` for xlsx native cells. Adapters emit spec tags only.

### v1.2 — Indicator tables vs period tables
> - **What happened:** A valuation ratio table mixes units per row (P/L is a multiple, Market Cap is BRL, Div Yield is a fraction). A single per-column spec can't cover it.
> - **Why it matters:** Forcing one spec misformats rows; emitting per-row specs complicates the table builder + template.
> - **Fix:** Two section flavours. Multi-period tables use per-column specs with native numbers. Key-value indicator tables use `_kv_section()` which pre-formats each value to a string and sets the column to `text`. xlsx indicator cells become text (acceptable — you don't sum P/L values), while period cells stay native.

---

*Last updated: 2026-07-25 (v1.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
