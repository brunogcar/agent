<- Back to [Notify Overview](../NOTIFY.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
def notify(
    action:        str,   # "send" | "schedule" | "cancel" | "list"
    title:         str = "",
    message:       str = "",
    timeout:       int = 5,
    delay_minutes: int = 0,
    job_id:        str = "",
) -> dict:
    '''Notification tool — send desktop alerts and schedule reminders.'''
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | **Yes** | One of `send`, `schedule`, `cancel`, `list` |
| `title` | `str` | No | Notification title. Default: `"Agent"` for `send`, `"Agent Reminder"` for `schedule`. |
| `message` | `str` | No | Notification body. **Required** for `send` and `schedule`. |
| `timeout` | `int` | No | Display duration in seconds. Default: 5. Used by `send` only. |
| `delay_minutes` | `int` | No | Delay before scheduled notification. **Required** for `schedule`. Must be > 0. |
| `job_id` | `str` | No | Job identifier. **Required** for `cancel`. |

---

## ⚡ Actions

### 📢 `send` — Immediate desktop notification

Sends a desktop notification immediately using the cross-platform fallback chain.

**Fallback chain:**
1. Windows → `plyer.notification.notify()` (native toast)
2. Linux → `notify-send` (libnotify)
3. Universal → `print()` to `sys.stderr`

**Return:**
```json
{
    "status": "sent",
    "title": "Research done",
    "message": "Tesla analysis complete",
    "method": "plyer"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"sent"` or `"error"` |
| `title` | `str` | Resolved title (default: `"Agent"`) |
| `message` | `str` | Notification body |
| `method` | `str` | Delivery method used: `"plyer"`, `"notify-send"`, or `"console"` |

**Error cases:**
- Missing `message` → `{"status": "error", "error": "message is required for send"}`

---

### ⏰ `schedule` — Schedule a delayed notification

Queues a notification for future delivery via APScheduler `BackgroundScheduler`.

**Config requirement:** `apscheduler` must be installed.

**Return:**
```json
{
    "status": "scheduled",
    "job_id": "reminder_1234567890",
    "message": "Check autocode results",
    "run_at": "2026-07-04 18:00:00",
    "delay_minutes": 10
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"scheduled"` or `"error"` |
| `job_id` | `str` | Unique identifier for cancellation |
| `message` | `str` | Notification body |
| `run_at` | `str` | ISO-formatted scheduled time |
| `delay_minutes` | `int` | Original delay requested |

**Error cases:**
- Missing `message` → `{"status": "error", "error": "message is required for schedule"}`
- `delay_minutes <= 0` → `{"status": "error", "error": "delay_minutes must be > 0 for schedule"}`
- APScheduler not installed → `{"status": "error", "error": "APScheduler not installed. Run: pip install apscheduler"}`
- Schedule failure → `{"status": "error", "error": "Schedule failed: {exception}"}`

---

### ❌ `cancel` — Cancel a scheduled notification

Removes a scheduled job from APScheduler and the in-memory registry.

**Return:**
```json
{
    "status": "cancelled",
    "job_id": "reminder_1234567890"
}
```

**Error cases:**
- Missing `job_id` → `{"status": "error", "error": "job_id is required for cancel"}`
- Scheduler not running → `{"status": "error", "error": "Scheduler not running"}`
- Cancel failure → `{"status": "error", "error": "Cancel failed: {e} (job may already have run)"}`

---

### 📋 `list` — List all scheduled notifications

Returns all jobs currently in the APScheduler job store, enriched with registry metadata.

**Return:**
```json
{
    "status": "ok",
    "jobs": [
        {
            "job_id": "reminder_1234567890",
            "run_at": "2026-07-04 18:00:00",
            "title": "Agent Reminder",
            "message": "Check autocode results"
        }
    ],
    "count": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"ok"` or `"error"` |
| `jobs` | `list` | Scheduled jobs with metadata |
| `count` | `int` | Number of scheduled jobs |

**Error cases:**
- Scheduler not running → `{"status": "ok", "jobs": [], "count": 0, "note": "Scheduler not running"}`

---

## 🔒 Security

*(Fill this section with relevant info from edits and refactors. Add security considerations as they are learned.)*

Current considerations:
- `subprocess.run(["notify-send", ...])` is called with hardcoded arguments. No shell injection risk.
- Job IDs are generated from `time.time()` — not cryptographically random, but sufficient for notification scheduling.

---

## 📤 Output & Status Schema

All actions return `dict` with notification-specific status values (not the generic `success`/`failure` pattern):

| Status | Meaning | Actions |
|--------|---------|---------|
| `sent` | Immediate notification delivered | `send` |
| `scheduled` | Reminder queued for future delivery | `schedule` |
| `ok` | Query/list operation succeeded | `list` |
| `cancelled` | Scheduled job removed | `cancel` |
| `error` | Operation failed | Any |

> **Note:** These are documented in `ToolResult` as valid notification-specific states.

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
