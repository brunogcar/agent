<- Back to [Tracer Overview](../TRACER.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| Pre-v1 | 2026-07-04 | Initial implementation. Structured logging, trace ID propagation, dual output (stderr + JSONL), bounded memory, thread-safe, graceful structlog fallback. |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

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

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
