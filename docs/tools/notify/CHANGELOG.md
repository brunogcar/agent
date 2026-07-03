<- Back to [Notify Overview](../NOTIFY.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| Pre-v1 | 2026-07-04 | Initial implementation. Single-file `tools/notify.py` with 4 actions: `send`, `schedule`, `cancel`, `list`. |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| 4 actions (`send`, `schedule`, `cancel`, `list`) | ✅ Pre-v1 | Single-file implementation in `tools/notify.py` |
| Cross-platform notifications | ✅ Pre-v1 | Windows (`plyer`), Linux (`notify-send`), console fallback |
| APScheduler integration | ✅ Pre-v1 | `BackgroundScheduler` with lazy import |
| In-memory job registry | ✅ Pre-v1 | `_job_registry` dict tracks scheduled job metadata |
| Special status schema | ✅ Pre-v1 | `sent`/`scheduled`/`ok`/`cancelled`/`error` instead of generic `success` |
| Graceful fallback | ✅ Pre-v1 | Never silently fails; always prints to console |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| **File split into `notify_ops/` subpackage** | Split monolithic `tools/notify.py` into `tools/notify_ops/` with `_registry.py`, `state.py`, `client.py`, `utils.py`, and `actions/{send,schedule,cancel,list}.py`. Follow the `web` tool pattern. | P0 |
| **Add `@meta_tool` + `@register_action` auto-discovery** | Generate `Literal` enum for `action` param, dynamic docstring, no central wiring. | P0 |
| **Add `conftest.py` + split tests** | Reuse existing `tests/tools/notify/test_notify.py` content across new focused test files: `test_send.py`, `test_schedule.py`, `test_cancel.py`, `test_list.py`, `test_error_handling.py`. | P0 |
| **Integrate `https://ntfy.sh/` with Docker** | Replace or augment desktop notifications with `ntfy.sh` push notifications. Run via Docker container. Enables remote/headless notifications. | P1 |
| **Standardize return format with `ok()`/`fail()`** | Currently returns raw `dict`. Should use `core/contracts.py` `ok()`/`fail()` for consistency with other tools. | P1 |
| **Add `reset_state()` for test isolation** | Close scheduler and clear `_job_registry` between tests. Follow `web_ops/state.py` pattern. | P1 |
| **Persist job registry to disk** | Currently in-memory only. Jobs lost on restart. Add JSON file persistence in `workspace/.notify_jobs/`. | P2 |
| **Add `recurring` action** | Cron-style recurring notifications via APScheduler `CronTrigger`. | P2 |
| **Add `modify` action** | Update title/message/time of an existing scheduled job without cancelling and re-creating. | P2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Email/SMS notifications** | Out of scope for notify tool. Use dedicated integrations or workflows. | Skip |
| 2 | **Persistent database backend for jobs** | In-memory + JSON file is sufficient. Full DB overkill for notification scheduling. | Skip |
| 3 | **Web UI for managing notifications** | Out of scope. Use `action="list"` and `action="cancel"` via tool calls. | Skip |
| 4 | **Notification history/log** | Not needed for current use case. Jobs are ephemeral. | Skip |
| 5 | **Rich media attachments** | Desktop notification APIs have limited support. Out of scope. | Skip |

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
