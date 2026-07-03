<- Back to [RUNTIME Overview](../RUNTIME.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **No HTTP dependency** — runtime modules never import from `gateway_backend`, `tools`, or `workflows`. This is a one-way dependency: consumers import from runtime, never the reverse.
2. **Never change `RLock()` to `Lock()`** — The reentrant lock prevents deadlock when `touch()` is called inside `inference_slot()`.
3. **Never remove `ensure_not_cancelled()` calls from write operations** — Ghost mutations corrupt memory and file state.
4. **Never skip stale lock file checks** — Lock files older than 5 minutes must be removed before skipping a restart. Process crashes leave orphaned lock files.
5. **Never hardcode LM Studio URLs or commands in the watchdog** — Use `cfg.runtime_provider` and `get_provider()`.
6. **Never make the timeout monitor a non-daemon thread** — It would prevent process exit. The monitor must be daemon.
7. **Never use `wait=False` in `shutdown_executor()`** — Zombie threads will corrupt state. Always `wait=True, cancel_futures=True`.
8. **Never forget Windows compatibility checks** — The watchdog uses Windows-specific `creationflags` and `STARTUPINFO`. Always check `sys.platform` before applying these. Linux/macOS don't have these attributes.

## ✅ ALWAYS DO

9. **Always add a health check for new subsystems** — Every critical component should be verifiable via `GET /health`.
10. **Always use `threading.RLock()` for nested calls** — Prevents deadlock in activity tracker and any future nested locking scenarios.
11. **Always call `ensure_not_cancelled()` before mutations** — Cancellation guards are the only defense against ghost mutations.
12. **Always check `can_execute()` before CB-protected operations** — Fail fast when circuit is open.
13. **Always reset circuit breakers between tests** — `_MY_CB.reset()` must be in a known state.
14. **Always include `error_code` in `fail()` calls** — Every error response must be programmatically consumable.
15. **Always test concurrency with real threading** — Activity tracker tests should use real `threading.Thread` instances, not just mocks.
16. **Always mock `asyncio.current_task()` and `task.cancelling()`** for cancellation tests.
17. **Always test lock file stale detection** — Create a lock file with an old timestamp and assert it gets removed.
18. **Always test cooldown behavior** — Mock time and assert restarts are skipped after threshold.
19. **Always test provider factory fail-fast** — Unknown provider names must raise immediately.
20. **Always test graceful shutdown** — Call `shutdown_executor()` and assert no zombie threads.

---

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for module details, [CHANGELOG.md](CHANGELOG.md) for version history.*
