<- Back to [Tracer Overview](../TRACER.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.1 | 2026-07-18 | Fixed `tracer.step/error/warning` 2-arg misuse across 10 callers — all now use `tracer.new_trace()` for a unique trace_id (was causing trace collisions in `_TraceStore` and ambiguous JSONL queries). Tests moved from `tests/core/tracer/` (2 files, ~10 tests) → `tests/core/observability/` (5 files, 147 tests) with a shared `conftest.py`. See [../../observability/CHANGELOG.md](../../observability/CHANGELOG.md) for the full subsystem changelog. |
| v1.3 | 2026-07-10 | Tracer implementation moved to `core/observability/tracer_engine.py`. `core/tracer.py` is now a thin facade that re-exports `tracer`, `Tracer`, `_TraceStore`, `generate_trace_id`, `_writer` (and other module-level names). 71+ callsites unchanged. See [../../observability/CHANGELOG.md](../../observability/CHANGELOG.md) for the full subsystem changelog. |
| Pre-v1 | 2026-07-04 | Initial implementation. Structured logging, trace ID propagation, dual output (stderr + JSONL), bounded memory, thread-safe, graceful structlog fallback. |

---

## ⚠️ Breaking Changes

| Version | Breaking Change | Migration |
|---------|----------------|-----------|
| v1.1 | `tests/core/tracer/` directory removed | Tests moved to `tests/core/observability/`. Patch paths updated from `patch("core.tracer._writer")` → `patch("core.observability.tracer_engine._writer")` (the facade re-export doesn't intercept writes from `Tracer` methods — see [../../observability/CHANGELOG.md](../../observability/CHANGELOG.md) v1.0 breaking change). No production callsites affected. |

> Note: The 71+ `from core.tracer import tracer` callsites are NOT broken by either v1.3 or v1.1. Only test code under `tests/core/tracer/` was affected, and v1.1 relocated + rewrote all of it.

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Dual output (stderr + JSONL) | ✅ Pre-v1 | Structured console + persistent queryable logs |
| Trace ID propagation | ✅ Pre-v1 | 8-char hex IDs across all operations |
| Bounded memory | ✅ Pre-v1 | 200-trace FIFO in-memory store |
| Graceful fallback | ✅ Pre-v1 | Standard logging if structlog missing |
| Trace query API | ✅ Pre-v1 | `GET /traces`, `GET /traces/{id}` |
| Daily rotation | ✅ Pre-v1 | New JSONL file per day |
| Thread safety | ✅ Pre-v1 | `threading.Lock()` on all writes |
| Auto-flush | ✅ Pre-v1 | `f.flush()` after every write |
| Silent I/O errors | ✅ Pre-v1 | Non-fatal disk errors ignored |
| Trace-Metrics integration | ✅ Pre-v1 | Qualitative + quantitative observability |
| Fix `tracer.step()` 2-arg usage | ✅ v1.1 | 10 callers now use `tracer.new_trace()` for a unique trace_id; `warning()` confirmed to require `trace_id` (the "No trace_id required" doc row was incorrect) |
| Test move + expansion | ✅ v1.1 | `tests/core/tracer/` (2 files, ~10 tests) → `tests/core/observability/` (5 files, 147 tests) with shared `conftest.py` |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Log compression | Gzip old JSONL files after 7 days | P2 |
| Log archival | Delete files older than 30 days | P2 |
| Trace sampling | Drop low-importance traces to reduce volume | P2 |
| OpenTelemetry integration | Export to Jaeger/Zipkin for distributed tracing | P3 |
| Remote log shipping | Forward to Loki, ELK for multi-machine deployments | P3 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-18. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules. For the v1.3+ observability subsystem changelog, see [../../observability/CHANGELOG.md](../../observability/CHANGELOG.md).*
