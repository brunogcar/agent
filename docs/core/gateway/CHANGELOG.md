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

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| WebSocket support | Real-time task progress streaming | P1 |
| OpenAPI schema versioning | `v1/` prefix for backward compatibility | P2 |
| API key rotation | Support multiple valid secrets for zero-downtime rotation | P2 |
| Request logging middleware | Structured request/response logging to tracer | P2 |
| Add `response_model` to remaining endpoints | Lock down `/version`, `/tools`, `/memory/stats`, `/health` sub-endpoints | P1 |
| SQLite connection pooling | Use single long-lived connection instead of per-call open/close | P2 |
| ChromaDB warmup readiness check | Block or return 503 until warmup completes | P2 |
| uvicorn string reference test | Add test asserting `core.gateway.create_app` is importable | P3 |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for endpoint details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
