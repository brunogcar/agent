<- Back to [Browser Overview](../BROWSER.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add subcommand parsing to action handlers** — one action = one behavior.
2. **Never import Playwright at module level in `actions/`** — lazy imports only. The `factory.py` and `loop.py` handle all Playwright interaction.
3. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks. Internal dispatch wrappers keep `**kwargs` to absorb unused params.
4. **Never print to stdout** — MCP stdio corruption. Use `sys.stderr` if needed.
5. **Never create `.bak` files** — forbidden by project rules.
6. **Never touch `@meta_tool` or `@register_action` shared decorators** — use `help_text` for param docs. Infrastructure changes need separate commits.
7. **Never put non-action files in `browser_ops/actions/`** — auto-discovery imports everything.
8. **Never cache `cfg.workspace_root` at module level** — breaks test mocking. Use lazy imports in failure paths.
9. **Never skip `compileall` before `pytest`** — syntax errors crash with confusing tracebacks.
10. **Never rewrite entire files when surgical edits suffice** — preserve existing code.
11. **Never register actions outside the `browser` namespace** — `DISPATCH["browser"]` is the only valid key.
12. **Never forget `trace_id` in error messages** — all `fail()` calls must include `trace_id=trace_id`.
13. **Never hold `_browser_lock` across long operations** — keep lock scope minimal to prevent blocking other traces.
14. **Never use `repr()` or f-strings for JS injection** — always use `json.dumps()` when embedding user-controlled values into `page.evaluate()` strings.
15. **Never call `close()` without `trace_id`** — it will leak the context. Always pass the trace_id that was used for `navigate`.

## ✅ ALWAYS DO

16. **Always verify tests mock the correct import path** — `mock.patch` targets where the name is **looked up**, not where it is defined.
17. **Always add `trace_id` to tracer steps** — `tracer.step(trace_id, "browser", ...)` not `tracer.step("browser", ...)`.
18. **Always use `compileall` before `pytest`** — catches syntax errors early.
19. **Always update `conftest.py` when adding new mock methods** — new actions need their Playwright methods mocked.
20. **Always include `examples` in `@register_action`** — the LLM uses these for few-shot prompting.
21. **Always validate URL schemes in `navigate`** — reject `file://`, `javascript:`, `data:` before `urlparse` or network calls.
22. **Always forward `headless` to `_get_page`** — actions that acquire a page must pass the user's `headless` preference.
23. **Always test error paths** — malformed JSON, missing files, invalid selectors, empty inputs.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
