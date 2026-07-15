# ⏰ Schedule Tool

The `schedule()` tool schedules **cron / interval / one-shot jobs** that **deliver via notify** at fire time. v1.0 introduces it as a new meta-tool — `notify` stays focused on notification delivery; `schedule` owns the scheduling logic, offline missed-fire recovery, and iCal calendar sync.

**Key characteristics:**
- **9 actions via `@meta_tool`** — `add_cron` (5-field cron, 0=Sunday), `add_interval` (duration `10m`/`2h`/`1d`), `add_once` (ISO / `in 30m` / `9am`), `list`, `cancel`, `modify`, `history`, `sync_calendar` (iCal `.ics` URL), `test`. The `action: Literal[...]` type is auto-generated from `DISPATCH`.
- **`schedule_ops/` subpackage (13 files)** — thin `@tool @meta_tool` facade; all logic in `tools/schedule_ops/` (`_registry.py`, `__init__.py` auto-discovery, `state.py`, `helpers.py`, `actions/__init__.py` + 9 action files). Drop a new file in `actions/` to add a 10th action — no facade edits.
- **Standardized `ok()`/`fail()` responses** — `response.status` is `"success"`/`"error"`; semantic status (`scheduled`/`cancelled`/`modified`/`ok`/`synced`) in `data.action_status`.
- **Standard cron semantics (0=Sunday)** — `core/time_utils._build_cron_trigger` remaps the DOW field to APScheduler day-names, sidestepping APScheduler's `from_crontab` 0=Monday trap. `"0 9 * * 1"` = Monday 9am.
- **Offline missed-fire recovery** — if the server is offline when a job is due, `catch_up_missed_jobs()` (server.py startup daemon) computes missed fires, applies `misfire_grace` (default 24h) + `misfire_policy` (`skip`/`fire_last` [default]/`fire_all`), delivers via notify, advances `last_fired_at` (idempotent).
- **Delivery backend: notify (v1.0)** — `schedule(add_cron, cron="0 9 * * *", title="...", message="...")` builds the delivery internally; pass `delivery={...}` for full control. ntfy.sh / Slack / Discord / Telegram / email = v2.0+.
- **iCal sync** — `sync_calendar` fetches `.ics`, parses VEVENT DTSTART/SUMMARY/DESCRIPTION (TZID + VALUE=DATE aware), creates `add_once` jobs for upcoming events. RRULE + CalDAV two-way = v2.0+.
- **`core/time_utils.py`** — new shared tz-aware time module (`now`/`parse_iso`/`parse_human`/`parse_duration`/`cron_next_fire`/`compute_missed_fires`), reading `cfg.timezone` (`AGENT_TZ` env). Replaces the external `@mcpcentral/mcp-time` MCP dependency (removed from `mcp.json`).
- **Job persistence** — `_job_registry` at `agent_root/.schedule_jobs/jobs.json` (atomic write; mirrors `.understand/`, NOT `workspace/`).
- **`trace_id` + `duration_ms`** in every response.
- **NOT `PARALLEL_SAFE`** — owns a `BackgroundScheduler` singleton + shared `_job_registry`. In `_TOOL_MAP` (lazy) so `parallel` can dispatch to it, just not concurrently with itself.

---

## 🚀 Quick Start

```python
# Cron: 9am daily standup reminder (delivered via notify)
schedule(action="add_cron", cron="0 9 * * *", title="Standup", message="Daily standup time")

# Cron: 9am every Monday (0=Sunday → 1=Monday)
schedule(action="add_cron", cron="0 9 * * 1", name="weekly_report", message="Write weekly report")

# Interval: every 10 minutes heartbeat
schedule(action="add_interval", interval="10m", message="Heartbeat")

# One-shot: 30 minutes from now
schedule(action="add_once", run_at="in 30m", message="Coffee break")

# One-shot: at a specific clock time (today if future, else tomorrow)
schedule(action="add_once", run_at="9am", title="Meeting", message="Standup", fire_if_missed=true)

# One-shot: full ISO datetime
schedule(action="add_once", run_at="2026-07-16T09:00:00", message="Deploy")

# Full delivery spec (override title/message at the delivery level)
schedule(action="add_cron", cron="0 9 * * *",
         delivery={"tool":"notify","action":"send","title":"Standup","message":"Daily standup"})

# List all scheduled jobs
schedule(action="list")

# Cancel by job_id
schedule(action="cancel", job_id="cron_1234567890")

# Modify a job's schedule + misfire policy
schedule(action="modify", job_id="cron_123", cron="0 10 * * *", misfire_policy="fire_all")

# Recent deliveries (in-memory log)
schedule(action="history", limit=20)

# Sync a Google Calendar iCal feed → one-shot jobs per upcoming event
schedule(action="sync_calendar", calendar_url="https://calendar.google.com/calendar/ical/.../basic.ics")

# Test the delivery pipeline (no job created)
schedule(action="test")
```

---

## 🔧 Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `AGENT_TZ` | (system local) | Timezone for all tz-aware operations. Examples: `America/Sao_Paulo`, `Europe/London`, `UTC`. Empty = system local. |
| `APScheduler` | (required for scheduling) | `pip install apscheduler`. `test` works without it; all `add_*`/`list`/`cancel`/`modify`/`sync_calendar` need it. |

**Persistence file:** `agent_root/.schedule_jobs/jobs.json` (atomic write via `tmp` + `os.replace`; reloaded on startup by `_load_jobs()` + `_reload_jobs_into_scheduler()`).

---

## 📋 When to use `schedule` vs `notify`

| Need | Tool | Action |
|------|------|--------|
| Immediate desktop notification | `notify` | `send` |
| Reminder N minutes from now (simple) | `notify` | `schedule` |
| Cron-style recurring (daily/weekly/Monday) | `schedule` | `add_cron` |
| Interval recurring (every N minutes/hours) | `schedule` | `add_interval` |
| One-shot at a specific clock time / ISO | `schedule` | `add_once` |
| Calendar-driven reminders (iCal feed) | `schedule` | `sync_calendar` |
| Catch-up of missed fires while offline | `schedule` | (automatic at boot) |

`notify.schedule` (delay_minutes) is kept for simple "remind me in N minutes" — `schedule.add_once` is the richer replacement (ISO / human time / fire_if_missed / misfire_grace).

---

## 📁 Subfile Directory

| Document | Contents |
|----------|----------|
| [API.md](schedule/API.md) | Full action reference: signature, params, returns, examples, error codes for all 9 actions. |
| [ARCHITECTURE.md](schedule/ARCHITECTURE.md) | Source-code reference (13 files in `schedule_ops/`), module tree, dispatch flow, persistence + catch-up design, test layout. |
| [CHANGELOG.md](schedule/CHANGELOG.md) | Version history, breaking changes, completed, in-progress, deferred (v2.0 roadmap). |
| [INSTRUCTIONS.md](schedule/INSTRUCTIONS.md) | NEVER DO / ALWAYS DO rules, anti-patterns, misfire-policy guidance, troubleshooting. |
