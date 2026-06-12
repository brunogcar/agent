# MCP Agent Gateway Architecture

The Gateway is the HTTP edge of the MCP Agent Stack. It exposes the agent's cognitive runtime, tools, and workflows over a REST API so external clients (second PC, phone, messaging adapters) can interact with it.

## 1. Architectural Philosophy: The "Memory Pattern"

The Gateway strictly follows the **Thin Orchestrator / Memory Pattern** established in Phases 1-7.
- `core/gateway.py` is a **~10 line Thin Facade**. It exists purely for backward compatibility (`uvicorn core.gateway:app`).
- `core/gateway_backend/` is the **HTTP Engine**. It owns all transport, routing, schemas, and HTTP-specific persistence.
- `core/runtime/task_runner.py` owns **Process Governance** (Thread pools, timeouts).

## 2. Directory Structure

```text
core/
├── gateway.py <-- THIN FACADE (Imports create_app, exposes `app`)
│
├── gateway_backend/ <-- THE HTTP ENGINE
│ ├── factory.py <-- FastAPI creation, lifespan, middleware, exception handlers
│ ├── models.py <-- Pydantic schemas (Strict API Contracts)
│ ├── store.py <-- SQLite task journal (Pure functions)
│ ├── dispatcher.py <-- Tool routing logic (Static router)
│ ├── dependencies.py <-- Auth, Rate Limiting, and DI Providers
│ ├── exceptions.py <-- Custom domain exceptions
│ └── routes/ <-- Feature-based APIRouter modules
│ ├── tasks.py <-- /task, /result
│ ├── chat.py <-- /chat
│ ├── health.py <-- /health, /health/*
│ ├── metrics.py <-- /metrics, /autocode/graph
│ ├── traces.py <-- /traces
│ └── reports.py <-- /reports, /logs, /api/reports
│
├── runtime/
│ └── task_runner.py <-- ThreadPoolExecutor & timeout monitoring
```

## 3. Domain Boundaries (The Ironclad Rules)

To prevent the Gateway from reverting to a "God Module", the following dependency rules are strictly enforced:

1. **One-Way Dependencies**: `gateway_backend` may import from `runtime`, `tools`, and `workflows`. **None of those may ever import from `gateway_backend`.**
2. **No HTTP in Runtime**: `core/runtime/task_runner.py` knows nothing about FastAPI, HTTP, or SQLite. It only accepts Python callables.
3. **No App State Leakage**: Routes must never use `request.app.state.foo` to access shared resources. All shared resources must be injected via FastAPI's `Depends()` pattern.
4. **Pure Functions for Storage**: `store.py` uses per-operation SQLite connections and a global thread lock. It does not hold open connections.

## 4. Lifecycle & Middleware Stack

The Gateway uses FastAPI's modern `@asynccontextmanager` lifespan and a strict middleware stack (defined in `factory.py`):

1. **Lifespan Context**:
   - *Startup*: Spawns a daemon thread for non-blocking ChromaDB warmup. Initializes the `ThreadPoolExecutor`.
   - *Shutdown*: Drains the executor (`shutdown(wait=True, cancel_futures=True)`) to prevent zombie threads.
2. **CORS Middleware**: Configurable via `GATEWAY_CORS_ORIGINS` to prevent wildcard exposure in production.
3. **MaxBodySize Middleware**: Rejects payloads > 10MB (configurable) to prevent OOM crashes.
4. **Request-ID Middleware**: Injects `request.state.trace_id` (from `X-Request-ID` header or generates a UUID) for end-to-end observability.

## 5. Error Handling & API Contracts

### Centralized Exceptions
Routes contain **zero** `try/except` boilerplate for tool execution. If a tool fails, the route raises `ToolExecutionError` or `TaskNotFoundError`. Global handlers in `factory.py` catch these, log them to the `tracer` with the `trace_id`, and return standardized JSON.

### Strict Pydantic Contracts
All endpoints use `response_model` to lock the API contract.
- `TaskSubmitResponse`
- `TaskResultResponse`
- `ChatResponse`

This guarantees that internal refactors will never silently strip fields that external clients rely on.

## 6. Report Serving Endpoints (Phase 5)

The gateway serves generated reports and agent logs via static-file routes:

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/reports` | Bearer | JSON array of all reports with metadata |
| `GET /reports/{trace_id}/` | — | HTML directory listing of that trace's files |
| `GET /reports/{trace_id}/{filename}` | — | Serve a specific report file (HTML, JSON, SVG, etc.) |
| `GET /logs/` | Bearer | HTML directory listing of log files |
| `GET /logs/{filename}` | Bearer | Serve a specific log file (text/plain) |

**Security**: All file paths are resolved and checked to ensure they stay within `workspace/reports/` or `logs/agent/`. Directory traversal (`..`) is rejected.

**Usage**:
```bash
# List all reports
curl -H "Authorization: Bearer $GATEWAY_SECRET" http://localhost:8000/api/reports

# View a report in browser
open http://localhost:8000/reports/test-trace/index.html

# Download metrics for Grafana
curl http://localhost:8000/reports/test-trace/metrics.json
```

## 7. Testing Strategy

The Gateway test suite (`tests/core/gateway/test_gateway.py`) is divided into distinct layers:

- **Layer 1 (Pure Unit Tests)**: Tests `store.py` directly using isolated `tmp_path` SQLite databases.
- **Layer 2 (Route Tests via DI)**: Uses FastAPI's `TestClient` and `app.dependency_overrides` to inject mock stores, dispatchers, and runners. **Monkeypatching is strictly forbidden in route tests.**
- **Layer 3 (Integration)**: Tests the full lifespan startup/shutdown and real dependency wiring.

## 8. Historical Context (Preserved Fixes)

The codebase retains critical historical context in its comments:
- **P0-1**: Stdout pollution fixed (all logs go to `sys.stderr` to keep MCP stdio clean).
- **P0-2**: Insecure defaults fixed (Startup guard refuses to start in prod with `changeme` secret).
- **P1-3**: Workflow status fix (Dispatcher ensures `status` key is always present).
- **P1-7**: ChromaDB warmup (Prevents 60s timeout on first memory call).
