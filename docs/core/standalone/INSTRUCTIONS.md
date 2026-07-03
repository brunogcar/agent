<- Back to [Standalone Overview](../STANDALONE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never implement custom path resolution in helpers or handlers** — Use `core.path_guard.resolve_path()` exclusively. The old `file_ops` refactor had `_resolve()` and `_safe_resolve()` in `helpers.py` that duplicated path_guard logic. That was a bug.
2. **Never add `**kwargs` to `ok()` / `fail()`** — FastMCP schema breaks. Use `**meta` instead.
3. **Never skip `check_protected_file()` for write operations** — Protected files must be guarded. Reads are always allowed.
4. **Never forget `GIT_WORKSPACE_ONLY` when adding new git actions** — `init` and `clone` must be restricted to `WORKSPACE_ROOT`.
5. **Never use `threading.Lock()` instead of `RLock()` for nested calls** — Prevents deadlock in activity tracker and any future nested locking scenarios.
6. **Never create `.bak` files** — Forbidden by project rules.
7. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
8. **Never print to stdout** — MCP stdio corruption. Return dicts only.
9. **Never skip `compileall` before `pytest`** — Catches syntax errors early.
10. **Never forget to update `READ_OPERATIONS` / `WRITE_OPERATIONS` when adding file actions** — Unknown operations fail-open with a warning. Explicit sets prevent silent bypasses.
11. **Never pass an already-created coroutine to `retry_async_factory()`** — Factory must return fresh coroutine each call.
12. **Never call `on_failure()` before `is_retryable()`** — Non-retryable errors must NOT trip the circuit breaker.

## ✅ ALWAYS DO

13. **Always use `resolve_path()` before any filesystem operation** — Centralized, symlink-safe, cross-platform.
14. **Always include `error_code` in `fail()` calls** — Every error response must be programmatically consumable.
15. **Always test SSRF blocking** — Patch `core.net.security.is_safe_network_address` and assert blocked URLs return `fail`.
16. **Always test with explicit `cfg` values** — `MagicMock` causes comparison errors. Use `patch.object(cfg, 'key', value)`.
17. **Always patch where the name is looked up** — Not where it is defined.
18. **Always update this doc** when adding modules, changing return shapes, or modifying path guard rules.
19. **Always use `sorted()` in `__init__.py` glob** — `sorted(_actions_dir.glob("*.py"))` for deterministic import order.
20. **Always lazy-import heavy dependencies** — Import inside handler functions, not at module top, to avoid circular imports and slow startup.
21. **Always use a single shared `cfg` mock in `conftest.py`** — Patch all action modules to the same `MagicMock` object so mutations are visible to every handler.
22. **Always test the unknown action path** — `tool(action="nonsense")` must return `fail` with the usage hint.
23. **Always test content-type guards** — Set `response.headers = {"content-type": "..."}` and assert structured error.
24. **Always test retry behavior** — Mock `time.sleep` to avoid real delays, assert call count equals retry attempts.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for module details, [CHANGELOG.md](CHANGELOG.md) for version history.*
