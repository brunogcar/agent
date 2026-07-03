# 🔔 Notify Tool

The `notify()` tool sends desktop notifications and schedules reminders. It replaces the old separate `notify.py` + `scheduler.py` tools with a single meta-tool.

**Key characteristics:**
- **Cross-platform** — Windows (`plyer`), Linux (`notify-send`), universal console fallback
- **Graceful fallback** — never silently fails; always prints to console if desktop APIs fail
- **Scheduler integration** — APScheduler `BackgroundScheduler` for delayed reminders
- **Job registry** — in-memory tracking of scheduled jobs with metadata
- **Special status schema** — uses `sent`/`scheduled`/`ok`/`cancelled`/`error` (not generic `success`)

---

## 🚀 Quick Start

```python
# Send an immediate desktop notification
notify(action="send", title="Research done", message="Tesla analysis complete")

# Schedule a reminder for 10 minutes from now
notify(action="schedule", message="Check autocode results", delay_minutes=10)

# List all scheduled notifications
notify(action="list")

# Cancel a scheduled notification
notify(action="cancel", job_id="reminder_1234567890")
```

---

## ⚙️ Configuration

Current requirements:
- `apscheduler` (optional — required only for `schedule`/`cancel`/`list` actions)
- `plyer` (optional — Windows desktop notifications)

*(Fill this section with relevant info from edits and refactors. Add `.env` variables and Docker setup for `ntfy.sh` as they are learned.)*

---

## 🔄 When to Use vs Alternatives

*(Fill this section with relevant info from edits and refactors. Add comparison table as it is learned.)*

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](notify/ARCHITECTURE.md) | Module tree, design decisions, test coverage, source code reference |
| [API.md](notify/API.md) | Full tool signature, all actions, status schema, error handling |
| [CHANGELOG.md](notify/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](notify/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-04. See subfiles for detailed documentation.*
