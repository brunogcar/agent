<- Back to [Gateway Overview](../GATEWAY.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| Pre-v1 | 2026-07-04 | Initial implementation. Thin facade + `gateway_backend/` subpackage with 6 route modules, SQLite task store, bearer auth, rate limiting, centralized error handling. |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Thin facade extraction | ✅ Pre-v1 | `core/gateway.py` → `core/gateway_backend/` |
| Centralized exception handlers | ✅ Pre-v1 | Zero try/except in routes |
| Rate limiting | ✅ Pre-v1 | slowapi integration |
| Request ID middleware | ✅ Pre-v1 | `X-Request-ID` header tracking |
| Payload size limits | ✅ Pre-v1 | MaxBodySize middleware |
| Report serving | ✅ Pre-v1 | Static files with CSP + path traversal protection |
| Pydantic contract locking (partial) | ⚠️ Pre-v1 | `response_model` on only 3 of ~16 endpoints (`/task`, `/result/{id}`, `/chat`) — see [API.md](API.md#pydantic-contract-locking) |
| Direct tool dispatch fallback | ✅ Pre-v1 | Fixed: router `direct` decisions now invoke tool directly; only fall back to `research` when tool is unmapped, with `tracer.warning()` |

---

## ✅ v1.1 (2026-07-18)

| Feature | Notes |
|---------|-------|
| **WebSocket /ws endpoint** | Real-time task progress streaming. Client connects via WebSocket, submits a task, receives progress events as they happen (instead of polling /result/{trace_id}). Auth via ?token= query param. |
| **response_model on 6 endpoints** | /version, /tools, /memory/stats, /health/autocode, /health/circuit-breakers, /health/models now have Pydantic response models. Locks down the API contract + clean OpenAPI docs. |
| **SQLite connection pooling** | store.py now uses a singleton connection (was: per-call open/close). WAL mode + busy_timeout prevent lock contention. |
| **ChromaDB warmup readiness check** | /health returns 503 until ChromaDB warmup completes. mark_chromadb_ready() called by the lifespan warmup thread. |
| **uvicorn string reference test** | New test asserting core.gateway:create_app is importable + /ws route is registered. |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| WebSocket support | ✅ v1.1 — /ws endpoint with real-time progress streaming | — |
| OpenAPI schema versioning | `v1/` prefix for backward compatibility | P2 |
| API key rotation | Support multiple valid secrets for zero-downtime rotation | P2 |
| Request logging middleware | Structured request/response logging to tracer | P2 |
| Add `response_model` to remaining endpoints | ✅ v1.1 — 6 endpoints now have Pydantic response models | — |
| SQLite connection pooling | ✅ v1.1 — Singleton connection in store.py | — |
| ChromaDB warmup readiness check | ✅ v1.1 — /health returns 503 until warmup completes | — |
| uvicorn string reference test | ✅ v1.1 — test_uvicorn_import.py (3 tests) | — |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-18. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for endpoint details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
