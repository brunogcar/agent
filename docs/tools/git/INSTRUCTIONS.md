<- Back to [Git Overview](../GIT.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add subcommand parsing to action handlers** — one action = one behavior. No `message` as mini-DSL.
2. **Never use `operation` parameter** — removed in v1. Use `action` only.
3. **Never create wrapper functions inside `@meta_tool`** — return `fn` directly. `@tool` is a marker decorator.
4. **Never hardcode `Literal` values separate from DISPATCH** — DRY violation. DISPATCH is single source of truth.
5. **Never forget to delete `fn.__signature__`** — stale cache won't reflect annotation mutations.
6. **Never skip action name validation before `eval()`** — `^[a-z][a-z0-9_]*$` regex. Rejects dunder names, builtins, Unicode.
7. **Never use `str.isidentifier()` alone** — accepts `__import__`, dunder names.
8. **Never create shadow tools** — one `git()` tool with atomic actions, not `git_branch()`, `git_tag()`, etc.
9. **Never use AST introspection for action discovery** — DISPATCH dict is explicit and robust.
10. **Never patch FastMCP internal schema after registration** — patch `__annotations__` BEFORE `mcp.tool()(fn)`.
11. **Never leave orphaned old files when splitting** — delete `branch.py` when creating `branch_list.py` + `branch_create.py` + `branch_delete.py`.
12. **Never use `**kwargs` in tool function signatures** — breaks FastMCP schema generation. Exception: inside action handlers, `**kwargs` absorbs unused dispatcher params.
13. **Never add legacy aliases** — two ways to do the same thing = two failure modes.
14. **Never duplicate docstring sources** — DISPATCH `help_text` and `examples` are canonical. `@meta_tool` generates the rest.
15. **Never use `message` for non-human-readable values** — `target` = commit hash, branch name, tag name.
16. **Never forget to restart LM Studio after schema changes** — cached tool schemas require full restart.
17. **Never skip `compileall` before `pytest`** — syntax errors in new files crash pytest with confusing tracebacks.
18. **Never use `@meta_tool` without `@tool`** — `@meta_tool` alone won't register with MCP. `@tool` alone won't generate the `Literal` enum.
19. **Never store metadata as scattered attributes** — `__tool_metadata__` single object.
20. **Never use `needs_repo=False` for actions that require a repo** — per-action `needs_repo` lets the dispatcher validate uniformly.
21. **Never create annotated tags in `tag_create`** — lightweight only. Annotated tags = separate `tag_annotate` action.
22. **Never confuse `branch_create` with `checkout_new`** — `branch_create` = `git branch <name>` (pointer only). `checkout_new` = `git checkout -b <name>` (creates AND switches).
23. **Never forget to search entire codebase for old references** — after renaming params or actions, run `Select-String` across all `.py` files.
24. **Never skip test file cleanup when restructuring** — delete old test files. Verify no import references remain.
25. **Never remove `del fn.__signature__`** — `inspect.signature()` caches results per-function-object. Stale cache won't reflect annotation mutations.

## ✅ ALWAYS DO

26. **Use `target` for entity names, `message` for human-readable text** — semantic clarity for the LLM.
27. **Add new actions by creating a file + `@register_action`** — DISPATCH and schema auto-update via `@meta_tool`.
28. **Keep tool facade thin** — validation, dispatch, compression. Business logic lives in action handlers.
29. **Document design decisions in comments** — explain WHY, not just WHAT. Future AI auditors need context.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
