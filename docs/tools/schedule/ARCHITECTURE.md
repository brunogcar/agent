# Schedule Tool — Architecture

## Source-code reference (13 files in `schedule_ops/` + facade + time_utils)

| File | Responsibility |
|------|----------------|
| `tools/schedule.py` | `@tool @meta_tool` facade — validation, dispatch, `duration_ms`. Thin wrapper, no business logic. |
| `tools/schedule_ops/_registry.py` | `DISPATCH` dict + `@register_action` decorator. Duplicate registration raises `ValueError`. |
| `tools/schedule_ops/__init__.py` | Auto-imports `actions/*.py` so `@register_action` runs before `@meta_tool` reads `DISPATCH`. |
| `tools/schedule_ops/state.py` | All shared mutable state: `_scheduler` singleton + `_scheduler_lock`, `_job_registry`, `_delivery_log` (bounded 100), `_jobs_path()`/`_save_jobs()`/`_load_jobs()` (atomic JSON at `agent_root/.schedule_jobs/jobs.json`), `_reload_jobs_into_scheduler()`, `mark_fired()`, `catch_up_missed_jobs()` + helpers, `reset_state()` for test isolation. |
| `tools/schedule_ops/helpers.py` | `_get_scheduler()` (lazy singleton + load + reload), `_fire_job()` (delivery via notify — loose coupling), `_resolve_delivery()` (normalize spec), `_call_notify()`. |
| `tools/schedule_ops/actions/add_cron.py` | Cron-scheduled recurring job (5-field, 0=Sunday via `_build_cron_trigger`). |
| `tools/schedule_ops/actions/add_interval.py` | Interval-scheduled recurring job (APScheduler `IntervalTrigger`). |
| `tools/schedule_ops/actions/add_once.py` | One-shot job (APScheduler `DateTrigger`). |
| `tools/schedule_ops/actions/list.py` | List all jobs + computed `next_run`. |
| `tools/schedule_ops/actions/cancel.py` | Cancel by `job_id` (marks `cancelled`, removes from APScheduler). |
| `tools/schedule_ops/actions/modify.py` | Update schedule/delivery/misfire policy; re-creates trigger if schedule changed. |
| `tools/schedule_ops/actions/history.py` | Recent deliveries (in-memory log, most-recent first). |
| `tools/schedule_ops/actions/sync_calendar.py` | iCal `.ics` fetch + parse → `add_once` jobs. |
| `tools/schedule_ops/actions/test.py` | Fire a test delivery via notify (no job created). |
| `core/time_utils.py` | Shared tz-aware time module: `get_timezone`/`now`/`parse_iso`/`parse_human`/`parse_duration`/`to_utc`/`from_utc`/`format_dt`/`cron_next_fire`/`compute_missed_fires`/`_build_cron_trigger`. |

## Module tree
```
tools/
├── schedule.py                 # @tool @meta_tool facade (DISPATCH dispatch)
└── schedule_ops/
    ├── _registry.py            # DISPATCH + @register_action
    ├── __init__.py             # auto-imports actions/*.py
    ├── state.py                # singleton + _job_registry + persistence + catch_up
    ├── helpers.py              # _get_scheduler + _fire_job (→notify) + _resolve_delivery
    └── actions/
        ├── __init__.py
        ├── add_cron.py
        ├── add_interval.py
        ├── add_once.py
        ├── list.py
        ├── cancel.py
        ├── modify.py
        ├── history.py
        ├── sync_calendar.py
        └── test.py
core/
├── time_utils.py               # NEW — tz-aware time + cron helpers (shared w/ notify next commit)
└── config_backend/execution.py # cfg.timezone (AGENT_TZ env)
```

## Dispatch flow
```
LLM call → schedule(action=...)
  → @meta_tool validates action ∈ Literal[9 actions]
  → facade looks up DISPATCH["schedule"][action]["func"]
  → handler(**kwargs) → ok()/fail() envelope
  → facade adds duration_ms → return
```
Auto-discovery: `from tools import schedule_ops` triggers `__init__.py` → globs `actions/*.py` → each `@register_action` populates `DISPATCH`. Adding a 10th action = drop a file in `actions/` (no facade edit).

## Persistence + restart semantics
- **`_save_jobs()`** — atomic write (`tmp` + `os.replace`) to `agent_root/.schedule_jobs/jobs.json`. Best-effort (never crashes the action).
- **`_load_jobs()`** — read JSON into `_job_registry` (metadata only, no APScheduler re-add). Called by `_get_scheduler()` after start.
- **`_reload_jobs_into_scheduler(sched)`** — re-add future fires: cron/interval always; once only if `run_at > now`.
- **`catch_up_missed_jobs()`** — separate function (NOT in `_get_scheduler`) so it can run in a server.py daemon without blocking the first `schedule()` call. Guarded by `_catch_up_done` (once per process; `force=True` to re-run in tests).

## Offline recovery design (the key feature)
```
server boot → _start_schedule_catch_up() daemon thread
  → catch_up_missed_jobs()
    for each job in _job_registry (not cancelled):
      missed = _missed_fires_for_job(meta, now)   # (last_fired_at, now]
      missed = [f for f in missed if within grace]
      apply policy:
        skip      → deliver none
        fire_last → deliver most recent
        fire_all  → deliver each (cap 50)
      mark_fired(job_id, missed[-1] or now)        # idempotent
```
**Why this design** (vs alternatives):
- *"Always fire_all"* → notification storm after long outage. Dangerous.
- *"Always skip"* → silent data loss; heartbeats disappear.
- *External cron daemon* → violates local-first, platform-specific.
- *APScheduler misfire_grace_time alone* → only covers in-process misfires, NOT process-down time.

`last_fired_at` is the durable signal. `mark_fired` is called after every successful delivery (live + catch-up). Accepted tradeoff (v1.0): if the process crashes between delivery and `mark_fired`, the next boot may re-deliver once (rare double-fire). A `firing`-state field (strict mode) is deferred to v2.0 if double-fires bite.

## Cron DOW remap (subtle APScheduler trap)
APScheduler's `CronTrigger.from_crontab` treats numeric `day_of_week` as **0=Monday**, NOT standard cron's 0=Sunday. So `"0 9 * * 1"` would fire **Tuesday** (1=Tuesday in APScheduler) instead of Monday. `core/time_utils._build_cron_trigger` parses the crontab DOW field (`*`, `*/N`, `a-b`, `a,b`, names) and remaps each to unambiguous day **names** (`sun`/`mon`/...), which APScheduler interprets correctly regardless of numeric convention. Standard cron semantics preserved.

## Delivery backend (loose coupling)
`_fire_job` → `_call_notify` → `from tools.notify import notify; notify(**delivery)`. Works whether notify is legacy (raw-dict return) or v1.0 (`ok`/`fail` envelope) — we only inspect `result.get("status")` defensively. NEVER hard-imports `notify_ops` (not present in this commit). v1.0 validates `delivery.tool == "notify"`; other backends raise `ValueError` → `fail(INVALID_PARAM)`.

## Test layout
```
tests/core/test_time_utils.py            # 51 tests — tz, parsing, cron, missed-fires
tests/tools/schedule/
├── conftest.py                          # reset_state (autouse), mock_cfg, mock_scheduler, mock_scheduler_none, mock_notify
├── test_dispatch.py                     # facade dispatch + Literal enum + unknown/empty action
├── test_add_cron.py                     # add_cron + DOW remap + validation
├── test_add_interval.py
├── test_add_once.py
├── test_list.py
├── test_cancel.py
├── test_modify.py
├── test_history.py
├── test_sync_calendar.py                # mocked httpx + .ics parsing
├── test_test.py
├── test_catch_up.py                     # offline recovery: skip/fire_last/fire_all + grace + idempotence
└── test_persistence.py                  # save/load/reload round-trip + atomic write
```

## Design decisions
- **`agent_root/.schedule_jobs/`** (not `workspace/`) — mirrors `.understand/`; job persistence is agent infrastructure, not user data.
- **3 misfire policies (not 4)** — grace is ALWAYS applied first; `fire_last_if_within_grace` is subsumed by `fire_last` post-grace. Simpler mental model.
- **`fire_all` capped at 50** — prevents notification storms on very-long outages; excess fires are counted in `fires_skipped`.
- **`once` jobs use `fire_if_missed`** (bool), not the policy trio — a one-shot either fires-once-if-missed or doesn't; "fire_all" is meaningless for one fire.
- **`list.py` filename** (not `list_workflows.py`) — aligns with `report_ops` convention; `list_workflows.py` is the legacy outlier being phased out (notify + workflow rename in the next commit).
