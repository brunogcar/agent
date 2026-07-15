<- Back to [Notify Overview](../NOTIFY.md)

# 🛡️ AI Notify Instructions

## ❌ NEVER DO

1. **Never silently fail a notification** — if desktop APIs fail, always fall back to console print. The user must always see the notification. `_send_notification()` always returns `(True, "console")` via the stderr fallback.
2. **Never require `apscheduler` at module import time** — lazy-import inside `_get_scheduler()` so `send` / `test` / `history` work without it installed. Only `schedule` / `cancel` / `list` / `recurring` need APScheduler.
3. **Never create `.bak` files** — forbidden by project rules. Use atomic writes (`tempfile.NamedTemporaryFile` + `os.replace`) instead — see `state._save_jobs()`.
4. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
5. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks. (Action handlers MAY accept `**kwargs` to swallow forward-compat params — the facade must not.)
6. **Never print to stdout** — MCP stdio corruption. Return dicts only. Console fallback uses `sys.stderr` explicitly.
7. **Never skip `compileall` before `pytest`** — catches syntax errors early.
8. **Never remove the console fallback** — it is the safety net for headless environments and missing dependencies.
9. **Never call `_send_notification` directly from an action handler** — use the helper via `helpers._send_notification(...)` (module-lookup pattern, NOT direct import). The `mock_scheduler` fixture in `conftest.py` patches `tools.notify_ops.helpers._get_scheduler` — direct imports would capture the original function at module-load time and bypass the patch. The same applies to `_get_scheduler()`.
10. **Never bypass `_save_jobs()` after registry changes** — `schedule`, `cancel`, `recurring`, and `modify` all mutate `_job_registry` and MUST call `state._save_jobs()` after. Skipping it leaves the persistence file out of sync with the in-memory registry (jobs won't survive process restart).
11. **Never call `state.reset_state()` in production code** — it shuts down the scheduler + nukes `_job_registry` + `_delivery_log`. It is TEST-ONLY and is called by the autouse `reset_notify_state` fixture in `conftest.py` before AND after each test.
12. **Never access `state._scheduler` directly from an action handler** — always go through `helpers._get_scheduler()` so the singleton is initialized on first use and persisted jobs are re-loaded.
13. **Never use a wrapper / `functools.partial` as the `@register_action` handler** — `@meta_tool` introspects the raw callable's signature for `Literal[...]` generation. Wrappers shadow the parameter introspection. The `func` reference in `DISPATCH` must be the raw callable.
14. **Never reuse a `job_id`** — `job_id` is generated from `int(time.time())` in `schedule`/`recurring`. If you call `schedule` twice in the same second, the second call's `add_job(..., id=job_id)` will fail APScheduler's `replace_existing=False` default. Always generate a fresh `job_id` per call.
15. **Never expand `notify` beyond the 8 actions without a clear delivery-vs-scheduling split** — notify stays focused on notification delivery. Richer scheduling logic (calendar sync, CRON_TZ, human-readable cron parsing, recurring task execution) belongs in the future `schedule` tool. See [ARCHITECTURE.md → Future `schedule` Tool Integration Plan](ARCHITECTURE.md#-future-schedule-tool-integration-plan).
16. **Never use generic `"success"`/`"error"` as the semantic status** — `response.status` is `"success"`/`"error"` (standardized via `ok()`/`fail()`). The semantic status (`sent`/`scheduled`/`cancelled`/`ok`/`modified`) goes in `data.action_status`. Preserve this distinction exactly.

## ✅ ALWAYS DO

17. **Always follow the `@meta_tool` pattern** — The facade is decorated with `@tool` + `@meta_tool(DISPATCH.get("notify", {}), doc_sections=[...])`. The `action: Literal[...]` type and the docstring are auto-generated from `DISPATCH`. Adding a new action = drop a file in `actions/` — no edits to the facade needed.
18. **Always import `tools.notify_ops` in the facade BEFORE reading `DISPATCH`** — The auto-discovery in `notify_ops/__init__.py` must run before `@meta_tool` reads `DISPATCH` for `Literal` generation. The facade does `from tools import notify_ops  # noqa: F401` for this side effect.
19. **Always use the module-lookup pattern for helpers** — Action handlers do `from tools.notify_ops import helpers` then call `helpers._get_scheduler()` / `helpers._send_notification()`. Do NOT do `from tools.notify_ops.helpers import _get_scheduler` — that captures the function at module-load time and bypasses the `mock_scheduler` fixture's patch.
20. **Always call `state._save_jobs()` after registry mutations** — `schedule`, `cancel`, `recurring`, `modify` all mutate `_job_registry` and must persist the change. The persistence file is the only way scheduled jobs survive process restarts.
21. **Always include `trace_id` in BOTH the `ok()` kwarg AND the data dict** — `ok({... "trace_id": trace_id}, trace_id=trace_id)`. The kwarg puts `trace_id` at the top level of the response (only when non-empty); the data dict inclusion makes it accessible at `result["data"]["trace_id"]` too. Tests assert both paths where applicable.
22. **Always include `error_code` in `fail()` calls** — Use the standardized codes: `MISSING_PARAM`, `INVALID_PARAM`, `NOT_FOUND`, `DEPENDENCY_MISSING`, `INTERNAL_ERROR`, `DELIVERY_FAILED`. Callers can branch on `error_code` instead of parsing the error message string.
23. **Always call `reset_state()` in the test conftest** — The `reset_notify_state` autouse fixture in `conftest.py` calls `state.reset_state()` before AND after each test. Without it, `_job_registry` and `_delivery_log` leak between tests, causing order-dependent failures.
24. **Always patch BOTH `tools.notify_ops.helpers.cfg` AND `tools.notify_ops.state.cfg` in tests** — Both modules do `from core.config import cfg` at module load. Patching only one leaves the other using the real `cfg` (same Python `from-x-import-y` pitfall as consult / parallel).
25. **Always test the console fallback path** — Mock `plyer` and `subprocess` to fail, assert `_send_notification` still returns `(True, "console")` and that the delivery log records `method="console"`.
26. **Always test cross-platform branches** — Patch `cfg.is_windows` to test Windows (plyer) vs Linux (notify-send) vs headless (console-only) paths.
27. **Always test scheduler-not-installed path** — Use the `mock_scheduler_none` fixture to simulate APScheduler not installed; assert graceful `DEPENDENCY_MISSING` error for `schedule`/`cancel`/`recurring`, and assert `list` returns empty list with note (NOT error).
28. **Always add `duration_ms` to the response** — The facade does this post-handler via `result["duration_ms"] = round((time.time() - start) * 1000)`. Do not duplicate this in handlers.
29. **Always validate cron expressions BEFORE adding the job** — `CronTrigger.from_crontab(cron)` raises `ValueError` on invalid syntax. Catch it at the action layer and return `fail(error_code="INVALID_PARAM")` rather than letting it bubble up as `INTERNAL_ERROR`.
30. **Always use `threading.Lock` for the scheduler singleton** — `state._scheduler_lock` prevents race conditions during concurrent `schedule` / `recurring` calls. `_get_scheduler()` acquires the lock before checking/initializing `_scheduler`.
31. **Always update this doc** when adding actions, changing return shapes, modifying the scheduler, or adding new persistence paths.
32. **Always update `docs/system_prompts/system_prompt.md`** when the call signature changes (e.g., new params, new actions). The system prompt examples are the LLM's primary reference.
33. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** Pre-v1 `notify` used semantic top-level `status` values (`sent`, `scheduled`, `ok`, `cancelled`) instead of the standardized `success` / `error` envelope. Callers that did `if result["status"] == "success": ...` would silently skip notify responses.
> - **Why it matters:** Other tools (`consult`, `parallel`, `vision`, `swarm`) all use the standardized `ok()` / `fail()` contract from `core.contracts`. Notify was the lone holdout — making it impossible to write generic `if result["status"] == "success"` handling across tools.
> - **Fix:** v1.0 standardizes on `ok()` / `fail()`. `response.status` is now `"success"` / `"error"` only. The semantic status is preserved in `data.action_status` (`sent` / `scheduled` / `cancelled` / `ok` / `modified`) so callers that branched on `"sent"` can migrate to `data.action_status == "sent"`. This is a BREAKING CHANGE — documented in [CHANGELOG.md → Breaking Changes](CHANGELOG.md#-breaking-changes) with migration guidance.

> - **What happened:** In v1.0, the `mock_cfg` fixture initially patched only `core.config.cfg`. Tests using `state._save_jobs()` (which calls `_jobs_path()` → `cfg.workspace_root`) wrote to the real workspace instead of the `tmp_path`.
> - **Why it matters:** Python's `from core.config import cfg` creates a local binding to the `cfg` object at import time. Patching `core.config.cfg` after import doesn't affect existing bindings. Both `helpers.py` AND `state.py` do `from core.config import cfg`, so each has its own `cfg` name that must be patched individually.
> - **Fix:** The `mock_cfg` fixture patches BOTH `tools.notify_ops.helpers.cfg` AND `tools.notify_ops.state.cfg` with the same mock. This is the same Python `from-x-import-y` pitfall documented in `consult-v1.0-staging` and `parallel-v1.0-staging`.

> - **What happened:** Early v1.0 action handlers used `from tools.notify_ops.helpers import _get_scheduler` (direct import). The `mock_scheduler` fixture patches `tools.notify_ops.helpers._get_scheduler` — but the direct import had already captured the original function at module-load time, so the patch was bypassed and tests hit the real APScheduler singleton.
> - **Why it matters:** Tests must patch where the name is LOOKED UP, not where it's DEFINED. Direct imports create a second binding that the patch doesn't reach.
> - **Fix:** Action handlers use the module-lookup pattern: `from tools.notify_ops import helpers` then `helpers._get_scheduler()`. The lookup happens at call time against the module's current attribute, which IS what the patch replaces. The `consult_ops` pattern uses direct imports because it patches `cfg` / `llm` / `check_rate_limit` (data), not the helper functions themselves. Notify's `_get_scheduler` is a function that wraps `state._scheduler` in non-trivial ways (lazy import + start + load_jobs), so patching it directly is the cleanest test seam — hence the module-lookup pattern.

> - **What happened:** Early v1.0 had a state ↔ helpers circular import. `state._load_jobs()` wanted `helpers._send_notification` as the firing callback for re-loaded jobs, but `helpers.py` imports `state` (for the scheduler), so `state.py` importing `helpers.py` at module load created a cycle that crashed the import.
> - **Why it matters:** Module-load-time circular imports are a common Python footgun — they crash with `ImportError: cannot import name 'X' from partially initialized module 'Y'`.
> - **Fix:** `state._noop_fire` is a stub in `state.py` that lazy-imports `_send_notification` at fire time: `from tools.notify_ops.helpers import _send_notification; _send_notification(title, message)`. The lazy import happens on the first firing, well after module initialization. Verified working: scheduled + recurring jobs survive `state.reset_state()` + scheduler re-init.

> - **What happened:** The pre-v1 `notify` tool had a `test_notify.py` with 10 tests in one file. Adding a single new action required touching the existing test file, risking unrelated test breakage. The test count stayed at 10 across the entire pre-v1 lifetime.
> - **Why it matters:** Monolithic test files discourage coverage growth — every addition risks breaking unrelated tests in the same file.
> - **Fix:** v1.0 split into 10 files (1 conftest + 9 test files), each focused on one action (or the facade dispatch). Test count grew 10 → 85 with no friction. Adding a 9th action would mean dropping a new `test_<name>.py` file — no edits to existing tests.

> - **What happened:** Early v1.0 `cancel` deferred to `scheduler.remove_job` and silently popped missing keys from `_job_registry`. Tests showed this masked bugs: callers that called `cancel` on a typo'd `job_id` got silent success instead of an error.
> - **Why it matters:** The registry is the authoritative source of truth — a `job_id` not in the registry either already fired or never existed. Silent success on a missing `job_id` masks caller bugs.
> - **Fix:** v1.0 `cancel` fast-fails with `error_code="NOT_FOUND"` if `job_id` is not in `_job_registry`. This is a BREAKING CHANGE — documented in [CHANGELOG.md → Breaking Changes](CHANGELOG.md#-breaking-changes). Callers that called `cancel` defensively on already-fired jobs must now check `error_code` instead of relying on silent success.

> - **What happened:** Early v1.0 `modify` was specified to "update title/message of an existing scheduled job". Implementation discovered that APScheduler's `add_job(..., kwargs={...})` bakes the kwargs in at scheduling time — there's no `update_kwargs` API. The naive implementation that just updated `_job_registry` metadata worked for `list()` but didn't change the next fire's payload.
> - **Why it matters:** A `modify` that "succeeds" but doesn't actually change the next fire is misleading. Callers would assume the change took effect and be surprised when the next notification fired with the old title/message.
> - **Fix:** v1.0 documents this limitation explicitly in the `modify.py` docstring AND in [API.md → modify → v1.0 Limitation](API.md#-v10-limitation--metadata-only-not-reschedule). Callers who need the change to take effect on the next fire must use `cancel` + `schedule`/`recurring`. v1.1 will fix this by changing the firing callback to look up `_job_registry` by `job_id` at fire time (tracked in [CHANGELOG.md → In Progress](CHANGELOG.md#-in-progress--next-up)).

> - **What happened:** The `test` action module was initially named `test.py`. The auto-discovery glob in `notify_ops/__init__.py` picked it up correctly, but some IDEs and linters flagged it as a test module due to the `test_*.py` / `*_test.py` pytest discovery pattern.
> - **Why it matters:** Confusing tooling signals — a developer seeing `actions/test.py` might think it's a test file and not realize it's a registered action.
> - **Fix:** The module was renamed to `test_notify.py` (action_name still `"test"` — registered via `@register_action("notify", "test", ...)`). The module file name does NOT need to match the action_name; `@meta_tool` reads `DISPATCH` keys, not module file names. Same naming convention as `list_workflows.py` registering `action_name="list"`.

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
