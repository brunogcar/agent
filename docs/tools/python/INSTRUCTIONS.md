<- Back to [Python Overview](../PYTHON.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never remove `hash` from `SAFE_BUILTINS`** — DoS risk via collision attacks.
2. **Never remove `_STDOUT_LOCK`** — Cross-thread stdout clobbering is a real bug (BUGFIX-2).
3. **Never bypass AST validation** — `_validate_sandbox_ast()` is the authoritative security check. Fast-path tokens are supplementary.
4. **Never add modules to `BLOCKED_IMPORTS` without adding tests** — security boundary changes need coverage.
5. **Never add `os`, `sys`, `subprocess` to allowed lists** — These are the core security boundary. Use dedicated tools instead.
6. **Never remove temp file cleanup** — The `finally` block in `_run_subprocess()` must always delete the temp file.
7. **Never hardcode timeout values** — Always use `cfg.execution_timeout`.
8. **Never print to stdout** — MCP stdio corruption. Return dicts only. Use `sys.stderr` for debug logs only.
9. **Never create `.bak` files** — forbidden by project rules.
10. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
11. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
12. **Never skip `compileall` before `pytest`** — catches syntax errors early.
13. **Never expose to untrusted multi-tenant input** — The sandbox is defense-in-depth, not a security boundary against determined adversaries.

## ✅ ALWAYS DO

14. **Always test AST bypass vectors** — `__builtins__`, `__subclasses__`, `getattr`, dynamic subscripts, metaclass attacks.
15. **Always test thread safety** — Concurrent `python()` calls with `_STDOUT_LOCK`.
16. **Always test import blocking** — `os`, `sys`, `subprocess` must be rejected in `run_data`.
17. **Always test subprocess timeout** — Mock `cfg.execution_timeout` to a small value.
18. **Always test temp file cleanup** — Assert temp file is deleted after subprocess execution.
19. **Always include mode in error responses** — Consumers need to know which mode failed.
20. **Always update this doc** when adding modes, changing allowlists, or modifying security rules.

---

## 🚫 Anti-Patterns & Lessons Learned

*(Fill this section with relevant information from edits and refactors. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
