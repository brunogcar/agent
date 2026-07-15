# Schedule Tool — API Reference

**Facade:** `tools/schedule.py` → `schedule(action, ...)` — `@tool @meta_tool` thin dispatch wrapper.

**Response shape:** standardized `ok()`/`fail()` envelopes (`core.contracts`):
```json
{"status": "success", "data": {"action_status": "...", ...}, "error": null, "trace_id": "...", "duration_ms": 12}
{"status": "error",   "data": null, "error": "...", "error_code": "...", "trace_id": "..."}
```

## Common parameters (facade)

| Param | Type | Used by | Notes |
|-------|------|---------|-------|
| `action` | `Literal[...]` | all | Required. One of the 9 actions. |
| `name` | str | add_*, sync | Human label for the job. |
| `cron` | str | add_cron, modify | 5-field cron, **0=Sunday** (`"0 9 * * 1"` = Mon 9am). |
| `interval` | str | add_interval, modify | Duration: `"10m"`/`"2h"`/`"1d"`/`"1h30m"`. |
| `run_at` | str | add_once, modify | ISO \| `"in 30m"` \| `"9am"` \| `"2026-07-16 09:00"`. |
| `message` | str | add_*, test, modify | Delivery body (or use `delivery`). |
| `title` | str | add_*, test, modify | Delivery title (default = job name). |
| `delivery` | dict | add_*, modify | Full spec `{tool,action,title,message,...}`. v1.0 `tool` must be `"notify"`. |
| `job_id` | str | cancel, modify | From the add_* response. |
| `misfire_policy` | str | add_cron, add_interval, modify | `skip` \| `fire_last` (default) \| `fire_all`. |
| `misfire_grace` | str | add_*, modify | Duration, default `"24h"`. |
| `fire_if_missed` | bool | add_once, modify | Fire on next boot if `run_at` passed while offline (within grace). |
| `calendar_url` | str | sync_calendar | http(s) `.ics` URL. |
| `trace_id` | str | all | Observability threading. |

---

## Actions

### add_cron
Schedule a cron-style recurring job.
```python
schedule(action="add_cron", cron="0 9 * * *", title="Standup", message="Daily standup")
schedule(action="add_cron", cron="0 9 * * 1", name="weekly_report", message="Mon report", misfire_policy="fire_all")
```
**Returns:** `{action_status: "scheduled", job_id, name, cron, next_run, misfire_policy, misfire_grace}`.
**Errors:** `MISSING_PARAM` (no cron/message), `INVALID_PARAM` (bad cron/policy), `DEPENDENCY_MISSING` (no APScheduler), `INTERNAL_ERROR`.

### add_interval
Schedule an interval recurring job.
```python
schedule(action="add_interval", interval="10m", message="Heartbeat")
```
**Returns:** `{action_status: "scheduled", job_id, name, interval, next_run, misfire_policy, misfire_grace}`.
**Errors:** `MISSING_PARAM`, `INVALID_PARAM` (bad interval/policy), `DEPENDENCY_MISSING`, `INTERNAL_ERROR`.

### add_once
Schedule a one-shot job at `run_at`.
```python
schedule(action="add_once", run_at="in 30m", message="Coffee break")
schedule(action="add_once", run_at="2026-07-16T09:00:00", title="Meeting", message="Standup", fire_if_missed=true)
```
**Returns:** `{action_status: "scheduled", job_id, name, run_at, fire_if_missed, misfire_grace}`.
**Errors:** `MISSING_PARAM`, `INVALID_PARAM` (bad run_at / past time), `DEPENDENCY_MISSING`, `INTERNAL_ERROR`.
**Note:** `run_at` in the past is rejected — use `notify(action="send")` for immediate delivery.

### list
List all scheduled jobs + metadata.
```python
schedule(action="list")
```
**Returns:** `{action_status: "ok", jobs: [{job_id, name, kind, cron, interval, run_at, status, next_run, last_fired_at, misfire_policy, misfire_grace, fire_if_missed, source, delivery_title, delivery_message}], count}`. Returns empty list (not error) if scheduler unavailable.

### cancel
Cancel a job by `job_id`.
```python
schedule(action="cancel", job_id="cron_1234567890")
```
**Returns:** `{action_status: "cancelled", job_id}`.
**Errors:** `MISSING_PARAM`, `NOT_FOUND`, (job already fired/cancelled is a no-op).

### modify
Modify a job's schedule and/or delivery metadata. Only supplied fields change.
```python
schedule(action="modify", job_id="cron_123", cron="0 10 * * *")
schedule(action="modify", job_id="once_456", message="Updated text", misfire_policy="fire_all")
```
**Returns:** `{action_status: "modified", job_id, changed: [...]}`.
**Errors:** `MISSING_PARAM`, `NOT_FOUND`, `INVALID_STATE` (cancelled), `INVALID_PARAM` (kind mismatch / bad value), `INTERNAL_ERROR`.
**Note:** changing `cron`/`interval`/`run_at` re-creates the APScheduler trigger. Changing `delivery`/`title`/`message` updates the persisted spec (next fire uses it).

### history
Recent deliveries (in-memory log, most-recent first).
```python
schedule(action="history")          # last 20
schedule(action="history", limit=5) # last 5 (max 100)
```
**Returns:** `{action_status: "ok", deliveries: [{job_id, fire_time, title, message, catch_up, result_status, trace_id, timestamp}], count}`.

### sync_calendar
Sync an iCal `.ics` URL into `add_once` jobs.
```python
schedule(action="sync_calendar", calendar_url="https://calendar.google.com/calendar/ical/.../basic.ics")
```
**Returns:** `{action_status: "synced", calendar_url, events_found, events_scheduled, events_skipped_past, rrule_skipped, parse_errors, jobs: [job_id...]}`.
**Errors:** `MISSING_PARAM`, `INVALID_PARAM` (bad scheme), `DEPENDENCY_MISSING`, `CONNECT_ERROR` (fetch), `INVALID_PARAM` (parse).
**v1.0 scope:** VEVENT DTSTART/SUMMARY/DESCRIPTION; TZID + VALUE=DATE aware; upcoming events only. **Deferred:** RRULE recurrence, CalDAV two-way, VTODO/VALARM, auth.

### test
Fire a test delivery immediately via notify (no job created).
```python
schedule(action="test")
schedule(action="test", title="Ping", message="hello")
```
**Returns:** `{action_status: "ok", delivery_result}`.

---

## Error codes
`MISSING_PARAM`, `INVALID_PARAM`, `INVALID_STATE`, `NOT_FOUND`, `DEPENDENCY_MISSING`, `CONNECT_ERROR`, `INTERNAL_ERROR`.

## Offline recovery (`catch_up_missed_jobs`)
Not an action — runs automatically at server boot (daemon thread in `server.py`). For each persisted job:
1. Compute missed fires in `(last_fired_at, now]`.
2. Drop fires older than `misfire_grace` (default 24h).
3. Apply `misfire_policy`: `skip` (discard all) / `fire_last` (deliver most recent) / `fire_all` (deliver each, capped at 50).
4. Advance `last_fired_at` (idempotent — never re-processes the same window).

Catch-up deliveries are stamped `[catch-up for fire @ <time>]` so they're distinguishable from live fires in `history`.
