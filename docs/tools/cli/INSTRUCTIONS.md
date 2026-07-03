<- Back to [CLI Overview](../CLI.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add `action` parameter to `cli()`** — `@meta_tool` would try to patch it to `Literal[...]`. CLI is a meta-tool, not a direct dispatcher.
2. **Never remove `shell=False`** — This is the core security boundary. `shell=True` would bypass all other protections.
3. **Never add commands to `ALLOWED_COMMANDS` without considering `BLOCKED_FLAGS`** — A new binary might have dangerous flags that need blocking.
4. **Never forget to update patterns when renaming actions** — Stale action names in `patterns.py` cause silent dispatch failures. Example: `read` → `read_file`.
5. **Never use `@meta_tool` without `@tool`** — `@meta_tool` alone won't register with MCP. `@tool` alone won't generate the docstring.
6. **Never create wrapper functions inside `@meta_tool`** — Return `fn` directly. `@tool` is a marker decorator.
7. **Never forget to delete `fn.__signature__`** — Stale cache won't reflect annotation mutations.
8. **Never hardcode `Literal` values separate from DISPATCH** — DRY violation. DISPATCH is single source of truth.
9. **Never skip action name validation before `eval()`** — `^[a-z][a-z0-9_]*$` regex.
10. **Never use `str.isidentifier()` alone** — Accepts `__import__`, dunder names.
11. **Never create shadow tools** — One `cli()` tool with proxy actions, not `cli_git()`, `cli_file()`, etc.
12. **Never use AST introspection for action discovery** — DISPATCH dict is explicit and robust.
13. **Never patch FastMCP internal schema after registration** — Patch `__annotations__` BEFORE `mcp.tool()(fn)`.
14. **Never leave orphaned old files when splitting** — Delete old action modules when refactoring.
15. **Never skip test file cleanup when restructuring** — Delete old test files. Verify no import references remain.
16. **Never re-validate paths in proxy handlers** — The underlying tool (`file()`, `git()`) already validates. Calling `resolve_path` again creates dual validation paths.
17. **Never add shell operators to `ALLOWED_COMMANDS`** — `|`, `;`, `&&` are blocked by `SHELL_OPERATORS`, not by the allowlist.
18. **Never forget the `_CLI_META_DISPATCH` collision risk** — If adding a new namespace action that shares a name with an existing one, the docstring will show the last one. Document it.
19. **Never skip `compileall` before `pytest`** — Syntax errors in new files crash pytest with confusing tracebacks.
20. **Never use `**kwargs` in tool function signatures** — Breaks FastMCP schema generation. Exception: inside proxy handlers, `**kwargs` absorbs unused dispatcher params.
21. **Never store metadata as scattered attributes** — `__tool_metadata__` single object.
22. **Never forget to search entire codebase for old references** — After renaming params or actions, run `Select-String` across all `.py` files.
23. **Never change `command: str` to `action: str`** — CLI is natural-language, not action-based.
24. **Never split stacked decorators to one-handler-per-action** — Documented difference from git/file.
25. **Never add `needs_path_guard` per-action metadata** — Facade handles it uniformly.
26. **Never implement interactive mode** — Conflicts with MCP stdio transport.
27. **Never rewrite router logic** — Working, just needs clean integration.
28. **Never change proxy return type from `str` to `dict`** — CLI is human-facing.

## ✅ ALWAYS DO

29. **Keep tool facade thin** — Validation, dispatch, compression. Business logic lives in proxy handlers or underlying tools.
30. **Document design decisions in comments** — Explain WHY, not just WHAT. Future AI auditors need context.
31. **Keep proxy handlers thin** — Format output, delegate to underlying tool. No business logic.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
