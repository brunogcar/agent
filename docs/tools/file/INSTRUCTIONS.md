<- Back to [File Overview](../FILE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never add subcommand parsing to action handlers** — one action = one behavior.
2. **Never use `operation` parameter** — removed in v1. Use `action` only.
3. **Never create wrapper functions inside `@meta_tool`** — return `fn` directly.
4. **Never hardcode `Literal` values separate from DISPATCH** — DRY violation.
5. **Never forget to delete `fn.__signature__`** — stale cache won't reflect annotation mutations.
6. **Never skip action name validation before `eval()`** — `^[a-z][a-z0-9_]*$` regex.
7. **Never use `str.isidentifier()` alone** — accepts `__import__`, dunder names.
8. **Never create shadow tools** — one `file()` tool with atomic actions.
9. **Never use AST introspection for action discovery** — DISPATCH dict is explicit.
10. **Never patch FastMCP internal schema after registration** — patch `__annotations__` BEFORE `mcp.tool()(fn)`.
11. **Never leave orphaned old files when renaming** — delete `read.py` when creating `read_file.py`.
12. **Never skip test file cleanup when restructuring** — delete old test files.
13. **Never re-validate paths in action handlers** — the facade already validates. Handlers receive pre-resolved paths. Calling `_safe_resolve` again creates dual validation paths with inconsistent logic.
14. **Never add `force` requirement to read-only actions** — only `delete_file`, `move_file` (overwrite), `copy_file` (overwrite), and `edit_file` need explicit confirmation.

## ✅ ALWAYS DO

15. **Use `path` for file paths, `source`/`destination` for move/copy** — semantic clarity.
16. **Add new actions by creating a file + `@register_action`** — DISPATCH auto-updates via `@meta_tool`.
17. **Keep tool facade thin** — validation, dispatch, compression. Business logic in action handlers.
18. **Document design decisions in comments** — explain WHY, not just WHAT.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
