# 🔔 Notify Tool

The `notify()` tool sends desktop notifications and schedules reminders. v1.0 refactors it from a single-file 247-line `@tool` function into a thin `@tool @meta_tool` facade that dispatches to 8 action handlers in the `notify_ops/` subpackage via the `DISPATCH` registry.

**Key characteristics:**
- **8 actions via `@meta_tool`** — `send` (immediate desktop notification), `schedule` (APScheduler `DateTrigger` one-shot), `cancel` (remove job by `job_id`), `list` (enumerate jobs + metadata), `recurring` (cron-style via `CronTrigger.from_crontab`), `modify` (update job metadata), `history` (in-memory delivery log), `test` (fixed test notification). The `action: Literal[...]` type is auto-generated from `DISPATCH`.
- **`notify_ops/` subpackage (11 files)** — Facade is a 154-line thin `@tool @meta_tool` dispatch wrapper; all logic lives in `tools/notify_ops/` (`_registry.py`, `__init__.py` auto-discovery, `state.py`, `helpers.py`, `actions/__init__.py` + 8 action files). Auto-discovery: drop a new file in `actions/` to add a 9th action — no facade edits needed.
- **Standardized `ok()` / `fail()` responses** — `response.status` is `"success"` / `"error"` only (matches `consult` / `parallel` / `vision` / `swarm` pattern). Semantic status (`sent` / `scheduled` / `cancelled` / `ok` / `modified`) preserved in `data.action_status`.
- **Job persistence** — `_job_registry` persisted to `workspace/.notify_jobs/jobs.json` via atomic write (`tmp` + `os.replace`). `_load_jobs()` re-hydrates on startup — scheduled + recurring jobs survive process restarts.
- **In-memory delivery log** — Bounded to 50 entries (`_MAX_DELIVERY_LOG`); powers the `history` action. NOT persisted (debugging aid, not audit trail).
- **Cross-platform fallback** — Windows (`plyer`), Linux (`notify-send`), universal console (`sys.stderr`) — never silently fails.
- **`trace_id` + `duration_ms` in every response** — Observability threading; facade adds `duration_ms` post-handler.
- **Lazy APScheduler import** — `send` / `test` / `history` work without `apscheduler` installed; only `schedule` / `cancel` / `list` / `recurring` need it.

**BREAKING v1.0:** Response format changed from raw dicts with semantic top-level `status` (`sent` / `scheduled` / `ok` / `cancelled`) to standardized `ok()` / `fail()` envelopes. Semantic status moved to `data.action_status`. See [CHANGELOG.md](notify/CHANGELOG.md) for migration details.

---

## 🚀 Quick Start

```python
# Send an immediate desktop notification
notify(action="send", title="Research done", message="Tesla analysis complete")

# Schedule a reminder for 10 minutes from now
notify(action="schedule", message="Check autocode results", delay_minutes=10)

# Schedule a recurring 9am daily notification (cron syntax)
notify(action="recurring", cron="0 9 * * *", title="Standup", message="Daily standup time")

# List all scheduled + recurring notifications
notify(action="list")

# Cancel a scheduled or recurring notification by job_id
notify(action="cancel", job_id="reminder_1234567890")

# Update a job's title and/or message (metadata only — see API.md for v1.0 limitation)
notify(action="modify", job_id="reminder_123", title="Updated Title")

# Show recently sent notifications (in-memory log, last 20)
notify(action="history")

# Send a test notification to verify the delivery pipeline works
notify(action="test")
```

---

## ⚙️ Configuration

| Dependency | Required? | Purpose |
|------------|-----------|---------|
| `apscheduler` | Optional — required only for `schedule` / `cancel` / `list` / `recurring` | APScheduler `BackgroundScheduler` + `DateTrigger` + `CronTrigger`. Lazy-imported inside `_get_scheduler()` — `send` / `test` / `history` work without it. |
| `plyer` | Optional — Windows desktop notifications | `plyer.notification.notify()` for native Windows toast. If missing or fails, falls through to console. |

**Persistence file:** `workspace/.notify_jobs/jobs.json` (atomic write via `tmp` + `os.replace`; reloaded on process startup by `_load_jobs()`).

---

## 🔀 When to Use vs Alternatives

| Need | Action / Tool | Why |
|------|---------------|-----|
| Immediate desktop alert | `notify(action="send")` | Cross-platform; always succeeds via console fallback |
| One-shot delayed reminder (N minutes) | `notify(action="schedule")` | APScheduler `DateTrigger`; survives restart via `jobs.json` |
| Recurring cron-style reminder | `notify(action="recurring")` | APScheduler `CronTrigger.from_crontab()`; 5-field Unix cron syntax |
| Cancel a scheduled/recurring job | `notify(action="cancel")` | Fast-fails with `NOT_FOUND` if `job_id` not in registry |
| List all pending jobs | `notify(action="list")` | Enriches APScheduler jobs with registry metadata |
| Update job title/message | `notify(action="modify")` | Metadata-only in v1.0 (does NOT reschedule — see [API.md](notify/API.md#-v10-limitation--metadata-only-not-reschedule)) |
| Verify delivery pipeline works | `notify(action="test")` | Fixed `title="Test"`, `message="Notification test successful"` |
| Check what was recently sent | `notify(action="history")` | Last 20 entries from in-memory delivery log (capped at 50) |
| Calendar sync (iCal / CalDAV) | ❌ future `schedule` tool | Out of scope for notify — notify stays focused on delivery |
| Push notification to phone | ❌ future `notify(action="ntfy")` | ntfy.sh Docker integration — see [CHANGELOG.md roadmap](notify/CHANGELOG.md#-suggested-roadmap-future-sessions) |
| Email notification | ❌ future `notify(action="email")` | SMTP integration — see [CHANGELOG.md roadmap](notify/CHANGELOG.md#-suggested-roadmap-future-sessions) |
| Slack / Discord / Telegram | ❌ future webhook backends | See [CHANGELOG.md roadmap](notify/CHANGELOG.md#-suggested-roadmap-future-sessions) |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](notify/ARCHITECTURE.md) | Source code reference (11 files in `notify_ops/`), module tree, dispatch flow (mermaid), 8-action pattern, job persistence (`workspace/.notify_jobs/jobs.json`), in-memory delivery log (max 50), future `schedule` tool integration plan, test layout (10 files, 85 tests), design decisions |
| [API.md](notify/API.md) | Full `@meta_tool` signature with 8 params (`action`/`title`/`message`/`timeout`/`delay_minutes`/`job_id`/`cron`/`trace_id`), 8 action sections (send/schedule/cancel/list/recurring/modify/history/test) with params/returns/examples, cron expression syntax, `modify` v1.0 limitation, error handling table, future API extensions |
| [CHANGELOG.md](notify/CHANGELOG.md) | v1.0 breaking changes (response format standardization, `cancel` fast-fail, `list` empty-vs-error), completed features (8 actions, `notify_ops/` 11 files, persistence, `trace_id`/`duration_ms`), suggested roadmap (ntfy/email/webhook/slack/discord/telegram/quiet_hours/priority/batch/templates/backend abstraction/separate `schedule` tool) |
| [INSTRUCTIONS.md](notify/INSTRUCTIONS.md) | AI editing rules — `@meta_tool` pattern, never call `_send_notification` directly from actions (use helpers module-lookup), never bypass `_save_jobs()` after registry changes, always call `reset_state()` in test conftest, never call `state._scheduler` directly, anti-patterns (8 entries) |

---

*Last updated: 2026-07-15 (v1.0). See subfiles for detailed documentation.*
