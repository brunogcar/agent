# Schedule Tool — Changelog

## v1.0 (2026-07-16) — Initial release

New tool. Schedules cron / interval / one-shot jobs that deliver via notify at fire time. Introduces `core/time_utils.py` as the shared tz-aware time module. Replaces the external `@mcpcentral/mcp-time` MCP dependency for our own tooling.

### Added
- **9 actions via `@meta_tool`**: `add_cron`, `add_interval`, `add_once`, `list`, `cancel`, `modify`, `history`, `sync_calendar`, `test`. `action: Literal[...]` auto-generated from `DISPATCH`.
- **`schedule_ops/` subpackage (13 files)** — facade + `_registry.py` + `__init__.py` auto-discovery + `state.py` + `helpers.py` + 9 action files.
- **`core/time_utils.py`** — tz-aware `now`/`now_iso`/`parse_iso`/`parse_human`/`parse_duration`/`to_utc`/`from_utc`/`format_dt`/`cron_next_fire`/`compute_missed_fires`/`_build_cron_trigger`. Reads `cfg.timezone` (`AGENT_TZ` env, default = system local). 51 unit tests.
- **`cfg.timezone`** (`AGENT_TZ` env) — single source of truth for tz, added to `core/config_backend/execution.py`.
- **Standard cron semantics (0=Sunday)** — `_build_cron_trigger` remaps DOW to APScheduler day-names, sidestepping the `from_crontab` 0=Monday trap.
- **Offline missed-fire recovery** — `catch_up_missed_jobs()` (server.py startup daemon) computes missed fires per job, applies `misfire_grace` (default 24h) + `misfire_policy` (`skip`/`fire_last` [default]/`fire_all`, cap 50), delivers via notify, advances `last_fired_at` (idempotent).
- **`mark_fired(job_id, fire_time)`** — durable `last_fired_at` update + persist after every successful delivery.
- **iCal sync** — `sync_calendar` fetches `.ics`, parses VEVENT DTSTART/SUMMARY/DESCRIPTION (TZID + VALUE=DATE aware), creates `add_once` jobs for upcoming events.
- **Job persistence** — `agent_root/.schedule_jobs/jobs.json` (atomic write; mirrors `.understand/`).
- **Router integration** — `_RE_DIRECT_SCHEDULE` heuristic + `schedule` in `ROUTER_TOOLS` + `ROUTER_SYSTEM_PROMPT` description.
- **`_TOOL_MAP`** — `schedule` added (lazy import). NOT in `PARALLEL_SAFE`.
- **`mcp.json`** — removed `@mcpcentral/mcp-time` entry (our tools no longer depend on it).

### Completed
- 9 actions, full test suite (`tests/tools/schedule/` + `tests/core/test_time_utils.py`).
- 5-file doc standard (INDEX + API/ARCHITECTURE/CHANGELOG/INSTRUCTIONS).
- server.py catch-up daemon thread.

### In progress
- (none)

### Deferred (v2.0+ roadmap)
- **Delivery backends** — ntfy.sh (Docker), Slack webhook, Discord webhook, Telegram bot, email (SMTP). v1.0 = notify only.
- **CalDAV two-way sync** — read+write, ETag-based change detection, auth (Basic/Bearer). v1.0 = iCal one-way fetch only.
- **RRULE recurrence expansion** — recurring iCal events currently schedule only the first occurrence; `rrule_skipped` is reported. Needs `dateutil.rrule` or `recurring-ical-events`.
- **VTODO / VALARM / EXDATE** — iCal tasks, per-event reminders, exception dates.
- **Strict no-double-fire mode** — a `firing` state field set before delivery + cleared after, for callers that cannot tolerate the rare double-fire on crash-between-deliver-and-mark.
- **notify v1.0 integration** — next commit swaps notify to `core/time_utils` (tz-aware), renames `notify_ops/actions/list_workflows.py`→`list.py` + `test_notify.py`→`test.py`, moves notify store to `agent_root/.notify_jobs/`.

### Breaking changes
- (none — new tool)
