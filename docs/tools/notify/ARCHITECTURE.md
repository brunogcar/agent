<- Back to [Notify Overview](../NOTIFY.md)

# 🏗️ Architecture

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `tools/notify.py` | `@tool` facade: action dispatch, validation, scheduler singleton, cross-platform notification |

*(Fill this section with relevant info from edits and refactors. Add new files as they are created during the split.)*

---

## 🌳 Module Tree

Current (pre-split):
```text
tools/notify.py
├── notify(action, ...)          # @tool facade — action dispatch, validation
├── _get_scheduler()             # BackgroundScheduler singleton with threading.Lock
├── _send_notification()         # Cross-platform: plyer → notify-send → console
├── _job_registry                # In-memory dict: job_id -> {title, message, run_at, status}
└── actions: send, schedule, cancel, list
```

Future (post-split — planned):
```text
tools/notify.py
├── notify(action, ...)          # @tool + @meta_tool facade — action dispatch
tools/notify_ops/
├── __init__.py                  # Auto-discovers actions/*.py
├── _registry.py                 # DISPATCH dict + @register_action decorator
├── state.py                     # _scheduler, _scheduler_lock, _job_registry, reset_state()
├── client.py                    # Cross-platform notification client
├── utils.py                     # Shared helpers
└── actions/
    ├── send.py                  # _action_send() — immediate desktop notification
    ├── schedule.py              # _action_schedule() — APScheduler delayed job
    ├── cancel.py                # _action_cancel() — remove scheduled job
    └── list.py                  # _action_list() — enumerate scheduled jobs
```

---

## 💡 Key Design Decisions

- **Single tool replacement** — `notify.py` replaces the old separate `notify.py` + `scheduler.py` tools. The LLM sees one unified interface.
- **Scheduler singleton with lock** — `_get_scheduler()` uses a `threading.Lock` to ensure only one `BackgroundScheduler` is created. Lazy-imports `apscheduler` to avoid hard dependency.
- **Cross-platform fallback chain** — `_send_notification()` tries Windows (`plyer`) → Linux (`notify-send`) → console (`sys.stderr`). Always returns `(True, method)` so nothing is silently swallowed.
- **In-memory job registry** — `_job_registry` tracks scheduled jobs with metadata (`title`, `message`, `run_at`, `status`). This is separate from APScheduler's internal job store and enables rich `list` output.
- **Special status schema** — Uses notification-specific statuses (`sent`, `scheduled`, `ok`, `cancelled`, `error`) instead of generic `success`. Documented in `ToolResult` as valid notification states.
- **Lazy APScheduler import** — `from apscheduler.schedulers.background import BackgroundScheduler` happens inside `_get_scheduler()`, not at module top. Allows `send` action to work without `apscheduler` installed.
- **Console fallback as feature, not bug** — `sys.stderr` print ensures the user always sees the notification, even in headless environments or when desktop APIs are unavailable.

---

## 🧪 Testing

```powershell
# Run all notify tests
.\venv\Scripts\python tests/tools/notify/ -W error --tb=short -v

> **Note:** Ensure `pytest` resolves to your venv. If not, use `python -m pytest` or the full venv path (`venv\Scripts\pytest.exe` on Windows, `venv/bin/pytest` on Unix).
```

**Test coverage:**

*(Fill this section with relevant info from edits and refactors. Add test file breakdown as tests are split into new files.)*

Planned test files (reusing existing `tests/tools/notify/test_notify.py`):
- `conftest.py` — Shared fixtures: `reset_scheduler()`, `mock_cfg_for_notify()`
- `test_send.py` — Immediate notification tests (cross-platform mock, fallback chain)
- `test_schedule.py` — APScheduler job creation, delay validation, job_id generation
- `test_cancel.py` — Job removal, missing job_id, already-run jobs
- `test_list.py` — Empty list, populated list, scheduler-not-running
- `test_error_handling.py` — Unknown action, missing required params, scheduler not installed

**Mock strategy:**
- Mock `plyer.notification.notify` for Windows path
- Mock `subprocess.run` for Linux `notify-send` path
- Mock `sys.stderr` for console fallback path
- Mock APScheduler `BackgroundScheduler` for schedule/cancel/list tests
- Patch `cfg.is_windows` to test cross-platform branches

---

*Last updated: 2026-07-04. See [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
