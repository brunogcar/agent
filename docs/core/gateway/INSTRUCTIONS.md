<- Back to [Gateway Overview](../GATEWAY.md)

# 🛡️ AI Gateway Instructions

## ❌ NEVER DO

1. **Never add logic to `core/gateway.py`** — all implementation belongs in `core/gateway_backend/`. The facade is one line: `app = create_app()`.
2. **Never create reverse dependencies** — `gateway_backend` may import from `runtime`, `tools`, `workflows`. Never the reverse.
3. **Never monkeypatch route internals in tests** — route tests must use `app.dependency_overrides`, never `unittest.mock.patch` on route internals.
4. **Never print to stdout** — all output goes to `sys.stderr` to keep MCP stdio clean.
5. **Never skip auth on routes** — every route except `/health` and `/version` must use `Depends(check_auth)`.
6. **Never remove security guards** — startup guard for default secret in production, rate limiting, payload size limits, path traversal checks.
7. **Never create `.bak` files** — forbidden by project rules.
8. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
9. **Never skip `compileall` before `pytest`** — catches syntax errors early.

## ✅ ALWAYS DO

1. **Always use response_model on endpoints** — v1.1: All public endpoints should have a Pydantic response model. This locks the API contract, strips internal fields, and generates clean OpenAPI docs.
2. **Always use the singleton SQLite connection** — v1.1: store.py uses a singleton connection. Never call db.close() on it (the connection lives for the process lifetime).
3. **Always check ChromaDB readiness** — v1.1: /health returns 503 until warmup completes. Use mark_chromadb_ready() to signal readiness from the lifespan.

10. **Always use Pydantic `response_model` on all endpoints** — never return raw dicts from routes. Lock down the contract.
11. **Always use lazy imports in dispatcher** — tool imports must remain inside the dispatch function, not at module level.
12. **Always trace everything** — every request must have a `trace_id` (from header or generated). All exceptions must log with `trace_id`.
13. **Always maintain rate limiting** — if slowapi is unavailable, implement a basic fallback.
14. **Always use `app.dependency_overrides` in route tests** — inject mock stores, dispatchers, and runners.
15. **Always patch pytest to `D:\mcp\agent\venv\Scripts\pytest.exe`** — per project workflow.
16. **Always include `-W error` and `--tb=short` in pytest commands** — clean output, catch warnings.
17. **Always update this doc** when adding endpoints, changing response shapes, or modifying auth/security.

## 🚫 Anti-Patterns & Lessons Learned

*(No entries yet. Add lessons here as they are learned from future refactors and bug fixes. When an AI assistant encounters a bug, fix, or architectural insight during editing, add it here with:*

> - **What happened:** The symptom or bug
> - **Why it matters:** The impact
> - **Fix:** The solution or pattern to follow

*Fill this section with relevant information during edits and refactors.)*

---

*Last updated: 2026-07-18. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for endpoint details, [CHANGELOG.md](CHANGELOG.md) for version history.*
