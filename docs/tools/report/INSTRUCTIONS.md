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

## ✅ ALWAYS DO

17. **Always verify templates render standalone** — `{% extends %}` + `{% block %}` structure must be complete.
18. **Always match template variable names to builder data structures** — `tab.name` vs `sec.title`, `tab.sections` vs flat `tabs`.
19. **Always pair `| safe` with pre-sanitization** — if you need `| safe` for syntax, sanitize the string first.
20. **Always update tests when refactoring templates** — test data structures must match template expectations.
21. **Always add `{% block scripts %}` for template-specific JS** — Chart.js, Mermaid init, etc.
22. **Always use `compileall` before `pytest`** — catches syntax errors early.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
