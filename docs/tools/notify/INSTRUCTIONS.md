<- Back to [Notify Overview](../NOTIFY.md)

# 🛡️ AI Notify Instructions

## ❌ NEVER DO

1. **Never silently fail a notification** — if desktop APIs fail, always fall back to console print. The user must always see the notification.
2. **Never require `apscheduler` at module import time** — lazy-import inside `_get_scheduler()` so `send` works without it installed.
3. **Never create `.bak` files** — forbidden by project rules.
4. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
5. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
6. **Never print to stdout** — MCP stdio corruption. Return dicts only (console fallback uses `sys.stderr`).
7. **Never skip `compileall` before `pytest`** — catches syntax errors early.
8. **Never remove the console fallback** — it is the safety net for headless environments and missing dependencies.
9. **Never use generic `"success"` status** — notify uses `sent`/`scheduled`/`ok`/`cancelled`/`error`. Preserve these exactly.
10. **Never generate predictable job IDs for security-sensitive use** — current `time.time()` is fine for notifications, but do not use this pattern for security tokens.

## ✅ ALWAYS DO

11. **Always lazy-import APScheduler** — `from apscheduler.schedulers.background import BackgroundScheduler` inside `_get_scheduler()`, not at module top.
12. **Always validate `delay_minutes > 0`** for `schedule` — reject zero or negative delays with structured error.
13. **Always validate required params per action** — `message` for `send`/`schedule`, `job_id` for `cancel`.
14. **Always test the console fallback path** — mock `plyer` and `subprocess` to fail, assert `sys.stderr.write` is called.
15. **Always test cross-platform branches** — patch `cfg.is_windows` to test Windows vs Linux vs headless paths.
16. **Always test scheduler-not-installed path** — uninstall `apscheduler` or mock `ImportError`, assert graceful error.
17. **Always patch where the name is looked up** — after file split, patch `tools.notify_ops.actions.send._send_notification`, not `tools.notify._send_notification`.
18. **Always update this doc** when adding actions, changing return shapes, or modifying the scheduler.
19. **Always use `threading.Lock` for scheduler singleton** — prevents race conditions during concurrent `schedule` calls.
20. **Always clean up `_job_registry` on cancel** — `pop(job_id, None)` to prevent memory leaks from stale entries.
21. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
22. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
