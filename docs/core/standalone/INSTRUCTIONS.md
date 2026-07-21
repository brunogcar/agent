<- Back to [Standalone Overview](../STANDALONE.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never implement custom path resolution in helpers or handlers** — Use `core.path_guard.resolve_path()` exclusively. The old `file_ops` refactor had `_resolve()` and `_safe_resolve()` in `helpers.py` that duplicated path_guard logic. That was a bug.
2. **Never use `datetime.now()` directly in tools** — Use `core.time_utils.now()` (tz-aware). Naive `datetime.now()` breaks silently if the host timezone changes or DST transitions. The only exception is test code asserting specific instants.
3. **Never use `CronTrigger.from_crontab()` directly** — it treats DOW as 0=Monday (Python convention), NOT standard cron's 0=Sunday. Always use `core.time_utils._build_cron_trigger(cron, get_timezone())` which remaps DOW to day-names. `"0 9 * * 1"` = Monday 9am, not Tuesday.
4. **Never assume `cfg.timezone` is a valid tz name** — `get_timezone()` resolves it lazily and falls back to system local → UTC on invalid values. Always go through `get_timezone()`, never `ZoneInfo(cfg.timezone)` directly.
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

> - **What happened:** `check_protected_file` returned `(True, "")` (allow) for unknown operations. New write actions added to tools but forgotten in `WRITE_OPERATIONS` would silently bypass protection on protected files.
> - **Why it matters:** A new tool action like `compress_file` (a write operation) would be allowed on `server.py` or `core/config.py` without any check, potentially corrupting infrastructure files.
> - **Fix:** Fail-closed — return `(False, error_msg)` for unknown operations. New actions must be explicitly added to `READ_OPERATIONS` or `WRITE_OPERATIONS` in `core/path_guard.py`.

> - **What happened:** `resolve_workspace_path` lacked the path traversal guard that `resolve_agent_path` had. A path like `../../secrets.txt` would escape the workspace sandbox.
> - **Why it matters:** Malicious or buggy code could read/write files outside the workspace, violating the sandbox boundary.
> - **Fix:** Added `target.relative_to(self.workspace_root.resolve())` check, mirroring `resolve_agent_path`. Raises `PermissionError` on traversal.

---

## `core/symbol_offload.py` rules

### NEVER DO
- Never store the full content in state AND the SymbolRef — pick one. The whole point is to keep state compact.
- Never offload small content (< 5 items / < 500 chars) — the SymbolRef overhead is larger than the content.
- Never delete the offloaded file while the SymbolRef is still in state — `drill_down()` will return `None`.

### ALWAYS DO
- Always check `is_symbol_ref(value)` before calling `drill_down(value)` — not all values are SymbolRefs.
- Always use `offload_to_file()` with a meaningful `field_name` — it becomes the filename.
- Always pass `trace_id` so files are grouped per-trace in `workspace/.symbols/{trace_id}/`.


---

*Last updated: 2026-07-25 (v1.5 — added atomic_write.py + backoff_retry.py).*
