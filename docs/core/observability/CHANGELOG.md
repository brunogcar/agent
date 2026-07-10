<- Back to [Observability Overview](OBSERVABILITY.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.0 | 2026-07-10 | Moved from `core/tracer.py` (now thin facade), `core/tracer_reader.py`, `core/metrics.py`, `workflows/helpers/checkpoint.py` into `core/observability/`. All four modules co-located as `tracer_engine.py`, `reader.py`, `metrics.py`, `checkpoint.py`. `core/tracer.py` kept as a thin facade so 71+ files importing `from core.tracer import tracer` don't need to change. |
| Pre-v1 | 2026-07-04 | Initial implementation. Structured logging, trace ID propagation, dual output (stderr + JSONL), bounded memory, thread-safe, graceful structlog fallback. |

---

## ⚠️ Breaking Changes

| Version | Breaking Change | Migration |
|---------|----------------|-----------|
| v1.0 | `patch("core.tracer._writer")` no longer intercepts writes from `Tracer` methods | Update tests to `patch("core.observability.tracer_engine._writer")`. The facade re-exports `_writer` for import compatibility, but `Tracer` method bodies resolve the name via `tracer_engine`'s module globals. |

> Note: The 71+ `from core.tracer import tracer` callsites are NOT broken — that's the whole point of the facade. Only test code that patches `core.tracer._writer` (a single test in `tests/core/tracer/test_tracer.py`) is affected.

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

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Log compression | Gzip old JSONL files after 7 days | P2 |
| Log archival | Delete files older than 30 days | P2 |
| Trace sampling | Drop low-importance traces to reduce volume | P2 |
| OpenTelemetry integration | Export to Jaeger/Zipkin for distributed tracing | P3 |
| Remote log shipping | Forward to Loki, ELK for multi-machine deployments | P3 |
| Fix `tracer.step()` 2-arg usage | Some callers use `tracer.step("health", "Health check")` which sets `trace_id="health"` — non-unique | P1 |
| Dedicated checkpoint tests | No `tests/core/observability/test_checkpoint.py` yet — only indirect coverage via workflow tests | P2 |
| Update `test_tracer.py` patch path | `patch("core.tracer._writer")` → `patch("core.observability.tracer_engine._writer")` for v1.0 facade semantics | P1 |
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

*Last updated: 2026-07-10. See [ARCHITECTURE.md](ARCHITECTURE.md) for module layout, [API.md](API.md) for function signatures, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
