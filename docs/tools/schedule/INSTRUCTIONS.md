# Schedule Tool — Instructions

## ALWAYS DO
- **Pass `message` (or `delivery.message`)** for every `add_*` action — it's the delivery body.
- **Use standard cron (0=Sunday)** — `"0 9 * * 1"` = Monday 9am. The DOW remap handles APScheduler's 0=Monday trap transparently; do NOT pre-remap yourself.
- **Pick the right misfire policy per job:**
  - Daily digest / report → `fire_last` (default) — you don't want 14 stale ones after a 2-week outage.
  - Hourly heartbeat / monitoring → `fire_all` — you want all missed pings (capped at 50).
  - Fire-and-forget / low-value → `skip` — silently drop missed fires.
- **Set `fire_if_missed=true` for important one-shots** (calendar events, deploy reminders) if you want them delivered on next boot even if `run_at` passed while offline.
- **Tune `misfire_grace`** — default 24h. For an hourly heartbeat, `"7d"` may be appropriate; for a daily digest, `"48h"`.
- **Use `schedule(add_once)` over `notify(schedule)`** for anything beyond "N minutes from now" — `add_once` accepts ISO / human time / `fire_if_missed` / `misfire_grace`.
- **Check `schedule(history)`** to verify deliveries actually fired (live + catch-up are both logged, with `catch_up: true` for offline-recovered fires).
- **Catch-up is automatic** — you do NOT need to call anything to recover missed fires; the server.py startup daemon runs `catch_up_missed_jobs()` once per boot.

## NEVER DO
- **NEVER hard-import `tools.notify_ops`** from schedule — it may not be present (this commit). Use `from tools.notify import notify` (loose coupling via the facade).
- **NEVER use `from_crontab` directly** for cron — it treats DOW 0=Monday, breaking standard cron. Always go through `core.time_utils._build_cron_trigger` (or `cron_next_fire` / `compute_missed_fires` which use it internally).
- **NEVER pass a past `run_at`** to `add_once` — it returns `INVALID_PARAM`. Use `notify(action="send")` for immediate delivery.
- **NEVER call `reset_state()` in production** — it nukes the scheduler + registry + delivery log. Test-only.
- **NEVER rely on APScheduler's `misfire_grace_time` alone** for offline recovery — it only covers in-process misfires, NOT process-down time. The `schedule` catch-up layer is what handles server-offline gaps.
- **NEVER expect `fire_all` to deliver unbounded fires** — it's capped at 50 per job per catch-up window (excess counted in `fires_skipped`). Tune `misfire_grace` to bound the window.

## Anti-patterns
- **Scheduling a job every second** — APScheduler can handle it, but notify delivery (subprocess/plyer) cannot keep up. Minimum practical interval is ~30s; prefer ≥1m.
- **Using `fire_all` for a daily digest with a 30-day grace** — 30 stale digests on boot. Use `fire_last` for digests.
- **Using `fire_last` for a heartbeat** — you lose the gap signal. Use `fire_all` (capped) for monitoring.
- **Trusting `next_run` for past once-jobs** — once a once-job has fired (or its `run_at` passed), `list` shows `next_run: ""`. Don't treat empty `next_run` as an error.
- **Modifying a cancelled job** — returns `INVALID_STATE`. Cancel is terminal; create a new job instead.

## Troubleshooting
- **"APScheduler not installed"** → `pip install apscheduler`. `test` works without it; all `add_*`/`list`/`cancel`/`modify`/`sync_calendar` need it.
- **Cron fires at the wrong day** → you hit the 0=Monday trap somewhere. Ensure you're using `schedule(add_cron)` (which remaps) and not constructing `CronTrigger.from_crontab` directly.
- **Cron fires at the wrong hour** → check `AGENT_TZ`. Cron fields are interpreted in the configured tz, not UTC. `"0 9 * * *"` = 09:00 in `AGENT_TZ`.
- **No catch-up after outage** → check the server.py startup log for `[server] Schedule catch-up: ...`. If `jobs_with_misses: 0`, either no jobs were due or `last_fired_at` was already advanced. Verify `last_fired_at` in `schedule(list)`; if empty, the job never fired (created_at is used as the lower bound instead).
- **Double-fire after a crash** → rare (process died between delivery and `mark_fired`). Accepted v1.0 tradeoff. If it bites, the strict `firing`-state mode is on the v2.0 roadmap.
- **`sync_calendar` found 0 events** → check `events_found` vs `events_scheduled` vs `events_skipped_past` vs `rrule_skipped` vs `parse_errors` in the response. Past events are skipped; RRULE events schedule only the first occurrence (counted in `rrule_skipped`).
