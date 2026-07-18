<- Back to [Observability Overview](OBSERVABILITY.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.1 | 2026-07-18 | Fixed `tracer.step()` 2-arg usage across 10 callers (now use `tracer.new_trace()`), fixed `reader._scan_disk()` log path (`cfg.log_path` → `cfg.agent_log_path`), fixed `checkpoint.sanitize_state()` `__fspath__` bug (`str()` → `os.fspath()`), moved + expanded tests from `tests/core/tracer/` (2 files, ~10 tests) → `tests/core/observability/` (5 files, 147 tests) with shared `conftest.py`. |
| v1.0 | 2026-07-10 | Moved from `core/tracer.py` (now thin facade), `core/tracer_reader.py`, `core/metrics.py`, `workflows/helpers/checkpoint.py` into `core/observability/`. All four modules co-located as `tracer_engine.py`, `reader.py`, `metrics.py`, `checkpoint.py`. `core/tracer.py` kept as a thin facade so 71+ files importing `from core.tracer import tracer` don't need to change. |
| Pre-v1 | 2026-07-04 | Initial implementation. Structured logging, trace ID propagation, dual output (stderr + JSONL), bounded memory, thread-safe, graceful structlog fallback. |

---

## ✅ v1.1 (2026-07-18)

| Fix | Files | Notes |
|-----|-------|-------|
| `tracer.step()` 2-arg usage → `new_trace()` | 10 callers (see below) | All callers that used a literal string or empty string as `trace_id` now use `tracer.new_trace()` to create a unique trace_id. Prevents trace collisions in `_TraceStore` and ambiguous JSONL queries. |
| `reader._scan_disk()` log path | `core/observability/reader.py` | Was scanning `cfg.log_path` (`logs/`) but `_FileWriter` writes to `cfg.agent_log_path` (`logs/agent/`). The non-recursive glob could never find the writer's files — disk-scan fallback was completely broken. Now scans `cfg.agent_log_path`. |
| `checkpoint.sanitize_state()` `__fspath__` | `core/observability/checkpoint.py` | Was using `str(state)` for Path-like objects, but `str()` falls back to `__repr__` for objects that define `__fspath__` but not `__str__` (e.g., `os.DirEntry`). Now uses `os.fspath(state)`. |
| Test move + expansion | `tests/core/tracer/` (deleted) → `tests/core/observability/` (new) | Old: 2 files, ~10 tests. New: 5 files, **147 tests**. |
| Shared `conftest.py` | `tests/core/observability/conftest.py` | New — provides `clean_store` (autouse), `mock_writer`, `isolated_tracer`, `isolated_log_path`, `isolated_checkpoint_dirs` fixtures. |
| `test_llm_tracer.py` updated | `tests/core/llm/test_llm_tracer.py` | `test_circuit_breaker_states_uses_tracer_step` now asserts the new unique trace_id (from `new_trace()`) instead of the old empty string `""`. |

**10 callers fixed (2-arg → `new_trace()`):**

| File | Before | After |
|------|--------|-------|
| `core/config_backend/validation.py` | `tracer.step("startup", ...)` | `_startup_tid = tracer.new_trace("startup", ...)` |
| `core/llm_backend/client.py` | `tracer.step("", "circuit_breaker", ...)` in a loop | ONE `new_trace()` before the loop |
| `core/runtime/health.py` | `tracer.step("health", ...)` | `_tid = tracer.new_trace("health", ...)` |
| `core/sleep_learn/feedback.py` | `tracer.step("daemon", ...)` | `_daemon_tid = tracer.new_trace("sleep_learn", ...)` |
| `core/sleep_learn/migrate.py` | `tracer.step("migration", ...)` + NameError bug (`_mig_tid` assigned inside try) | `_mig_tid` created at the TOP of the function (fixes NameError when `dry_run=True`) |
| `workflows/autocode_impl/helpers.py` | `tracer.step("autocode", ...)` per-iteration | ONE `new_trace()` before the loop |
| `core/memory_backend/janitor.py` | `tracer.error("janitor", ...)` | `_tid = tracer.new_trace("janitor", ...)` |
| `core/memory_backend/meta_learning.py` | `tracer.step("daemon", ...)` per cycle | One `new_trace()` per cycle |
| `core/kgraph/cleanup.py` | `tracer.warning("kg_cleanup", f"...")` — wrong-arity 2-arg call (`trace_id="kg_cleanup"`, `node=f"Failed..."`, `message=""`) | Proper 3-arg call with a unique trace_id |
| `core/memory_backend/maintenance.py` | 6× `tracer.error("", "maintenance", ...)` across 4 functions | Each function creates its own trace_id |

---

## ⚠️ Breaking Changes

| Version | Breaking Change | Migration |
|---------|----------------|-----------|
| v1.0 | `patch("core.tracer._writer")` no longer intercepts writes from `Tracer` methods | Update tests to `patch("core.observability.tracer_engine._writer")`. The facade re-exports `_writer` for import compatibility, but `Tracer` method bodies resolve the name via `tracer_engine`'s module globals. (v1.1: the canonical test path is now `core.observability.tracer_engine._writer`; the old `tests/core/tracer/` directory has been removed.) |

> Note: The 71+ `from core.tracer import tracer` callsites are NOT broken — that's the whole point of the facade. Only test code that patches `core.tracer._writer` is affected, and v1.1 moved all such tests to `tests/core/observability/` with the correct patch path.

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Co-located observability subsystem | ✅ v1.0 | 4 modules (`tracer_engine`, `reader`, `metrics`, `checkpoint`) under `core/observability/` |
| Thin facade for tracer | ✅ v1.0 | `core/tracer.py` re-exports `tracer`, `Tracer`, `_TraceStore`, `generate_trace_id`, `_writer`, etc. from `tracer_engine` |
| Dual output (stderr + JSONL) | ✅ Pre-v1 | Structured console + persistent queryable logs |
| Trace ID propagation | ✅ Pre-v1 | 12-char hex IDs across all operations |
| Bounded memory | ✅ Pre-v1 | 200-trace FIFO in-memory store |
| Graceful fallback | ✅ Pre-v1 | Standard logging if structlog missing; Prometheus helpers become no-ops if prometheus_client missing |
| Trace query API | ✅ Pre-v1 | `GET /traces`, `GET /traces/{id}` |
| Daily rotation | ✅ Pre-v1 | New JSONL file per day |
| Thread safety | ✅ Pre-v1 | `threading.Lock()` on all writes |
| Auto-flush + atexit close | ✅ Pre-v1 | `f.flush()` after every write, `atexit.register(_writer.close)` |
| Silent I/O errors | ✅ Pre-v1 | Non-fatal disk errors ignored |
| Trace-Metrics integration | ✅ Pre-v1 | Qualitative + quantitative observability |
| Append-only checkpoint journal | ✅ Pre-v1 | One JSONL file per trace, fsync on every write |
| Zombie detection + quarantine | ✅ Pre-v1 | `MAX_RESUMES=5` + consecutive-same-node-failure heuristic |
| Version validation | ✅ Pre-v1 | `_checkpoint_version` injected into restored state |
| `scan_incomplete()` boot recovery | ✅ Pre-v1 | 48-hour cutoff for server-boot crash scan |
| `sanitize_state()` recursive | ✅ Pre-v1 | Drops non-serializable objects, handles circular refs |
| Fix `tracer.step()` 2-arg usage | ✅ v1.1 | All 10 callers now use `tracer.new_trace()` for a unique trace_id |
| Fix `reader._scan_disk()` log path | ✅ v1.1 | Scans `cfg.agent_log_path` (was `cfg.log_path` — never found writer files) |
| Fix `sanitize_state()` `__fspath__` | ✅ v1.1 | Uses `os.fspath()` (was `str()` — fell back to `__repr__` for `os.DirEntry`) |
| Dedicated checkpoint tests | ✅ v1.1 | `tests/core/observability/test_checkpoint.py` — full coverage of sanitize_state, save/get, zombie quarantine, scan_incomplete |
| Update `test_tracer.py` patch path | ✅ v1.1 | Tests moved to `tests/core/observability/`; patch path is now `core.observability.tracer_engine._writer` |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Log compression | Gzip old JSONL files after 7 days | P2 |
| Log archival | Delete files older than 30 days | P2 |
| Trace sampling | Drop low-importance traces to reduce volume | P2 |
| OpenTelemetry integration | Export to Jaeger/Zipkin for distributed tracing | P3 |
| Remote log shipping | Forward to Loki, ELK for multi-machine deployments | P3 |
| Env-var configurable MAX_RESUMES | Currently a module-level constant; should be a cfg setting | P3 |
| Checkpoint journal compaction | Long-running workflows accumulate many entries; compact on resume | P3 |

---

## 🚫 Deferred / Out of Scope

| Feature | Why Deferred |
|---------|--------------|
| OpenTelemetry native trace export | Would require adding OTLP exporter deps; current JSONL + Prometheus covers single-machine deployments |
| Distributed tracing across processes | MCP Agent Stack is single-process; not needed |
| Real-time trace streaming via SSE/WebSocket | Gateway already has `GET /traces`; SSE streaming is a separate concern |
| Structured log forwarding to systemd/journald | Linux-only; out of scope for cross-platform agent |

---

*Last updated: 2026-07-18. See [ARCHITECTURE.md](ARCHITECTURE.md) for module layout, [API.md](API.md) for function signatures, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
