# 🌐 Gateway

The Gateway (`core/gateway.py`) is the **HTTP edge** of the MCP Agent Stack. It exposes the agent's cognitive runtime, tools, and workflows over a REST API so external clients (second PC, phone, browser, messaging adapters) can interact with it.

**Key characteristics:**
- **Thin facade pattern** — `core/gateway.py` is ~10 lines; all logic lives in `core/gateway_backend/`
- **Async task submission** — Submit tasks, get `trace_id` immediately, poll for results
- **Synchronous chat** — Block-and-wait for quick interactions
- **Bearer token auth** — Configurable secret, hard-stop in production with default
- **Rate limiting** — 30/min on `/chat`, 60/min on `/task` via slowapi
- **Centralized error handling** — Zero try/except boilerplate in routes
- **Contract-locked responses** — Pydantic `response_model` on every endpoint

---

## 🏗️ Architecture

### Component Map

```
core/gateway.py                     # Thin facade (~10 lines)
core/gateway_backend/
├── factory.py                      # FastAPI creation, lifespan, middleware, exception handlers
├── dependencies.py                 # Auth (Bearer token), DI providers
├── dispatcher.py                   # Tool/workflow routing from HTTP payloads
├── exceptions.py                   # TaskNotFoundError, ToolExecutionError
├── models.py                       # Pydantic request/response schemas
├── store.py                        # SQLite task store for async polling
└── routes/
    ├── tasks.py                    # POST /task, GET /result/{trace_id}
    ├── chat.py                     # POST /chat (synchronous)
    ├── health.py                   # /health, /version, /tools, /memory/stats, /health/*
    ├── metrics.py                  # /metrics (Prometheus), /autocode/graph (Mermaid)
    ├── traces.py                   # /traces, /traces/{trace_id}
    └── reports.py                  # /reports/*, /logs/*, /api/reports

core/runtime/
├── task_runner.py                  # ThreadPoolExecutor & timeout monitoring
└── activity_tracker.py             # Idle detection (tracker.touch() on every request)
```

### Request Flow

```mermaid
graph TD
    A["HTTP Client<br/>curl / fetch / phone / adapter"] --> B["Middleware Stack<br/>CORS → MaxBody → RequestID"]
    B --> C["check_auth()<br/>Bearer token + tracker.touch()"]
    C -->|Unauthorized| D["401 Unauthorized"]
    C -->|OK| E{Endpoint?}
    E -->|POST /task| F["Async Path<br/>store → task_runner → dispatcher"]
    E -->|POST /chat| G["Sync Path<br/>dispatcher.dispatch() → wait"]
    E -->|GET /result| H["Poll Path<br/>store._get_task()"]
    E -->|GET /health| I["Health Check<br/>dirs + LM Studio + ChromaDB"]
    E -->|GET /traces| J["Trace History<br/>tracer_reader"]
    E -->|GET /reports| K["Report Serving<br/>static files + CSP"]
    F --> L["dispatcher.dispatch()<br/>Tool or workflow routing"]
    G --> L
    L --> M["Result<br/>ok() or fail()"]
    M --> N["JSON Response<br/>Pydantic-validated"]
```

### Domain Boundaries (Ironclad Rules)

```mermaid
graph LR
    subgraph "May import →"
        GB["gateway_backend"]
        RT["runtime"]
        T["tools"]
        W["workflows"]
    end
    GB -->|"One-way"| RT
    GB -->|"One-way"| T
    GB -->|"One-way"| W
    RT -.->|"NEVER"| GB
    T -.->|"NEVER"| GB
    W -.->|"NEVER"| GB
```

| Rule | Description |
|------|-------------|
| **One-way dependencies** | `gateway_backend` may import from `runtime`, `tools`, `workflows`. None may import from `gateway_backend`. |
| **No HTTP in Runtime** | `task_runner.py` knows nothing about FastAPI, HTTP, or SQLite. It only accepts Python callables. |
| **No App State Leakage** | Routes never use `request.app.state.foo`. All shared resources injected via `Depends()`. |
| **Pure Functions for Storage** | `store.py` uses per-operation connections + global thread lock. No open connections. |

---

## 🚀 Lifecycle & Middleware Stack

### Startup / Shutdown

```mermaid
graph TD
    subgraph "Startup"
        A["Lifespan context<br/>@asynccontextmanager"] --> B["Spawn daemon thread<br/>ChromaDB warmup"]
        A --> C["init_executor()<br/>ThreadPoolExecutor(max_workers=10)"]
        A --> D["validate_config()<br/>Secondary config check"]
    end
    subgraph "Runtime"
        E["App serves requests"]
    end
    subgraph "Shutdown"
        F["shutdown_executor()<br/>wait=True, cancel_futures=True"] --> G["Join warmup thread<br/>timeout=5s"]
    end
    A --> E
    E --> F
```

### Middleware Order

| Order | Middleware | Config | Description |
|-------|-----------|--------|-------------|
| 1 | **CORS** | `GATEWAY_CORS_ORIGINS` (default `["*"]`) | Cross-origin request handling |
| 2 | **MaxBodySize** | `GATEWAY_MAX_BODY_MB` (default `10`) | Rejects POST/PUT/PATCH > limit with 413 |
| 3 | **RequestID** | Auto-generated UUID | Injects `request.state.trace_id`, echoes `X-Request-ID` header |

### ChromaDB Warmup

At startup, the gateway spawns a daemon thread that calls `recall("warmup", top_k=1)` to force ChromaDB to load the embedding model. This prevents 30-60s cold-start latency on the first real memory call.

| Behavior | Implementation |
|----------|---------------|
| Thread | Daemon thread (non-blocking) |
| Timeout | 60s hard timeout via `ThreadPoolExecutor` |
| On timeout | Proceeds in "degraded mode", logs warning |
| On success | Logs elapsed time to stderr |

> ⚠️ **Note:** The warmup is non-blocking — the server starts accepting requests before warmup completes. Early requests may hit cold ChromaDB.

---

## 📡 Endpoints

### Task Submission (Async)

#### `POST /task` — Submit Async Task

```bash
curl -X POST http://localhost:8000/task \
  -H "Authorization: Bearer $GATEWAY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"goal": "Research ChromaDB best practices", "workflow": "auto"}'
```

**Response:**
```json
{
  "trace_id": "abc-123-def",
  "status": "submitted",
  "poll_url": "/result/abc-123-def"
}
```

**Request Body (`TaskRequest`):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `goal` | `str?` | `null` | Task description (triggers workflow routing) |
| `workflow` | `str?` | `"auto"` | Workflow type (`auto`, `research`, `data`, `autocode`) |
| `tool` | `str?` | `null` | Direct tool name (bypasses workflow) |
| `action` | `str?` | `null` | Tool action |
| `params` | `dict?` | `null` | Tool-specific parameters |
| `platform` | `str?` | `"api"` | Source platform identifier |
| `user` | `str?` | `null` | User identifier |

**Flow:**
1. Validate request via Pydantic
2. Create trace via `tracer.new_trace()`
3. Store task in SQLite (`store._store_task()`)
4. Submit to `task_runner.run_background_task()` (300s timeout)
5. Return immediately with `trace_id` and `poll_url`

#### `GET /result/{trace_id}` — Poll for Result

```bash
curl -H "Authorization: Bearer $GATEWAY_SECRET" \
  http://localhost:8000/result/abc-123-def
```

**Response:**
```json
{
  "trace_id": "abc-123-def",
  "status": "success",
  "result": {"summary": "ChromaDB best practices include..."},
  "error": null,
  "elapsed": 12.3
}
```

**Status values:** `pending` → `running` → `success` | `failed` | `unknown`

**Fallback:** If task not found in SQLite, checks in-memory tracer for traces that completed before the store was updated.

---

### Chat (Synchronous)

#### `POST /chat` — Synchronous Chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $GATEWAY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is ChromaDB?"}'
```

**Response:**
```json
{
  "trace_id": "abc-123-def",
  "status": "success",
  "result": {"summary": "ChromaDB is an open-source vector database..."},
  "platform": "api"
}
```

**Request Body (`ChatRequest`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `str` | ✅ Yes | User message (becomes the goal) |
| `platform` | `str?` | No (default `"api"`) | Source platform |
| `user` | `str?` | No | User identifier |

**Use `/task` for long-running workflows.** `/chat` blocks until completion.

---

### Health & System

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | No | Full health check (dirs, LM Studio, ChromaDB, models) |
| `GET /health/autocode` | Bearer | Autocode-specific health (optional `?deep=true` for LM Studio probe) |
| `GET /health/circuit-breakers` | Bearer | LLM circuit breaker states per model |
| `GET /health/models` | Bearer | Check if required models are loaded in LM Studio |
| `GET /version` | No | Git commit, branch, environment |
| `GET /tools` | Bearer | List of available tools |
| `GET /memory/stats` | Bearer | ChromaDB collection counts and sizes |

#### Health Response

```json
{
  "status": "healthy",
  "timestamp": 1718820000,
  "env": "development",
  "checks": {
    "dir_agent_root": {"status": "ok", "path": "D:/mcp/agent"},
    "lm_studio": {"status": "ok", "url": "http://localhost:1234/v1"},
    "chromadb": {"status": "ok", "client": "initialized"},
    "models": {
      "planner": {"status": "ok", "model": "gemma-4-e2b-it@q5_k_s"},
      "executor": {"status": "ok", "model": "gemma-2-2b-it"}
    }
  }
}
```

#### Circuit Breaker Monitoring

```json
{
  "status": "ok",
  "breakers": {
    "gemma-4-e2b-it@q5_k_s": {"state": "closed", "failures": 0},
    "gemma-2-2b-it": {"state": "closed", "failures": 1},
    "lfm2-1.2b-tool": {"state": "half-open", "failures": 3}
  }
}
```

---

### Telemetry

| Endpoint | Auth | Content-Type | Description |
|----------|------|-------------|-------------|
| `GET /metrics` | Bearer | `text/plain` (Prometheus) | Node durations, task statuses, TDD iterations, LLM tokens |
| `GET /autocode/graph` | Bearer | `text/plain` (Mermaid) | Autocode state machine flowchart |

---

### Traces

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /traces` | Bearer | List recent traces (default limit: 10, configurable via `?limit=N`) |
| `GET /traces/{trace_id}` | Bearer | Full execution timeline for a specific trace |

**Trace retrieval priority:**
1. In-memory store (last 200 traces, fast)
2. JSONL disk scan (last 14 days, slow)

---

### Reports & Logs

| Endpoint | Auth | Content-Type | Description |
|----------|------|-------------|-------------|
| `GET /api/reports` | Bearer | `application/json` | JSON array of all reports with metadata |
| `GET /reports/{trace_id}/` | Bearer | `text/html` | HTML directory listing of trace files |
| `GET /reports/{trace_id}/{filename}` | Bearer | Various | Serve specific report file |
| `GET /logs/` | Bearer | `text/html` | HTML directory listing of log files |
| `GET /logs/{filename}` | Bearer | `text/plain` | Serve specific log file |

**Security:**
- All file paths resolved and checked to stay within `workspace/reports/` or `logs/agent/`
- Directory traversal (`..`) rejected via `Path.resolve().startswith()`
- CSP headers on HTML responses: `default-src 'self'; frame-ancestors 'none'; connect-src 'none'`
- Cache-Control: `no-store, private` on all responses
- Log file extension whitelist: `.jsonl`, `.json`, `.txt`, `.log`

---

## 🔀 Dispatcher

The dispatcher (`core/gateway_backend/dispatcher.py`) routes incoming payloads to the appropriate tool or workflow.

### Routing Logic

```mermaid
graph TD
    A["Incoming payload"] --> B{Has goal<br/>or tool='workflow'?}
    B -->|Yes| C{workflow='auto'?}
    C -->|Yes| D["router.route(goal)<br/>→ RoutingDecision"]
    C -->|No| E["Use specified workflow"]
    D --> F["run_workflow(wf_type, goal, ...)"]
    E --> F
    B -->|No| G{tool?}
    G -->|web| H["tools.web.web()"]
    G -->|python| I["tools.python_exec.python()"]
    G -->|memory| J["tools.memory_tool.memory()"]
    G -->|file| K["tools.file.file()"]
    G -->|git| L["tools.git.git()"]
    G -->|agent| M["tools.agent_tool.agent()"]
    G -->|report| N["tools.report_tool.report()"]
    G -->|notify| O["tools.notify.notify()"]
    G -->|cli| P["tools.cli.cli()"]
    G -->|vision| Q["tools.vision.vision()"]
    G -->|unknown| R["error: Unknown tool"]
```

### Tool List

| Tool | Import | Description |
|------|--------|-------------|
| `web` | `tools.web.web()` | Web scraping, search |
| `python` | `tools.python_exec.python()` | Python code execution |
| `memory` | `tools.memory_tool.memory()` | ChromaDB read/write |
| `file` | `tools.file.file()` | File operations |
| `git` | `tools.git.git()` | Git operations |
| `agent` | `tools.agent_tool.agent()` | Agent delegation |
| `report` | `tools.report_tool.report()` | Report generation |
| `notify` | `tools.notify.notify()` | Notifications |
| `cli` | `tools.cli.cli()` | CLI command execution |
| `vision` | `tools.vision.vision()` | Image analysis |
| `workflow` | `workflows.base.run_workflow()` | Multi-step workflows |

**All imports are lazy** (inside the function) to avoid circular imports and reduce startup cost.

---

## 🔐 Authentication & Security

### Bearer Token Auth

```mermaid
graph TD
    A["Request"] --> B["HTTPBearer(auto_error=False)"]
    B --> C{GATEWAY_SECRET<br/>== 'changeme'?}
    C -->|Yes| D["Allow all<br/>(dev mode, warn to stderr)"]
    C -->|No| E{Token<br/>matches?}
    E -->|Yes| F["Allow + tracker.touch()"]
    E -->|No| G["401 Unauthorized"]
```

**Every auth check also calls `tracker.touch()`** to update idle detection for background daemons.

### Security Guards

| Guard | Condition | Behavior |
|-------|-----------|----------|
| **Default secret in production** | `GATEWAY_SECRET == "changeme"` AND `ENV != "dev"` | **Hard stop** — `SystemExit(1)` |
| **Default secret in dev** | `GATEWAY_SECRET == "changeme"` AND `ENV == "dev"` | Warning to stderr, continue |
| **Rate limit: /chat** | 30 requests/minute per IP | 429 Too Many Requests |
| **Rate limit: /task** | 60 requests/minute per IP | 429 Too Many Requests |
| **Payload limit** | POST/PUT/PATCH > `GATEWAY_MAX_BODY_MB` | 413 Payload Too Large |
| **Path traversal** | Report/log serving | 403 Forbidden |
| **File extension** | Log serving | 400 if not `.jsonl/.json/.txt/.log` |

---

## 📊 SQLite Task Store

The async task store (`core/gateway_backend/store.py`) persists task state for polling.

### Schema

```sql
CREATE TABLE tasks (
    trace_id  TEXT PRIMARY KEY,
    status    TEXT NOT NULL DEFAULT 'pending',
    submitted REAL NOT NULL,
    completed REAL,
    result    TEXT,
    error     TEXT,
    payload   TEXT
);
```

### Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| Path | `{memory_root}/gateway_tasks.db` | SQLite database location |
| Journal mode | WAL | Write-ahead logging for concurrency |
| Busy timeout | 5000ms | Wait before SQLITE_BUSY error |
| WAL checkpoint | 1000 pages | Prevents unbounded `.wal` growth |
| Thread safety | `check_same_thread=False` | Cross-thread access |
| Lock | `threading.Lock()` | Global write lock |

### Task Lifecycle

```mermaid
graph LR
    A["POST /task<br/>_store_task()"] --> B["pending"]
    B --> C["_update_task('running')"]
    C --> D["running"]
    D --> E["dispatcher.dispatch()"]
    E -->|Success| F["_update_task('success', result)"]
    E -->|Error| G["_update_task('failed', error)"]
    E -->|Timeout (300s)| H["_update_task('failed', 'timeout')"]
    F --> I["Terminal state"]
    G --> I
    H --> I
```

---

## 🔧 Error Handling

### Centralized Exception Handlers

Routes contain **zero** `try/except` boilerplate for tool execution. If a tool fails, the route raises a domain exception. Global handlers in `factory.py` catch these:

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `TaskNotFoundError` | 404 | `trace_id` not found in store or tracer |
| `ToolExecutionError` | 500 | Tool or workflow fails during dispatch |
| `Exception` (catch-all) | 500 | Any unhandled exception |

### Response Format

All error responses follow a consistent schema:

```json
{
  "error": "Task not found",
  "trace_id": "abc-123-def",
  "detail": "trace_id 'abc-123-def' not found"
}
```

### Pydantic Contract Locking

All endpoints use `response_model` to lock the API contract:

| Model | Endpoint | Fields |
|-------|----------|--------|
| `TaskSubmitResponse` | `POST /task` | `trace_id`, `status="submitted"`, `poll_url` |
| `TaskResultResponse` | `GET /result/{id}` | `trace_id`, `status`, `result`, `error`, `elapsed` |
| `ChatResponse` | `POST /chat` | `trace_id`, `status`, `result`, `error`, `platform` |

This guarantees that internal refactors will never silently strip fields that external clients rely on.

---

## ⚙️ Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `GATEWAY_HOST` | `127.0.0.1` | REST API bind address |
| `GATEWAY_PORT` | `8000` | REST API port |
| `GATEWAY_SECRET` | `changeme` | Bearer token for authentication |
| `GATEWAY_CORS_ORIGINS` | `["*"]` | Allowed CORS origins (comma-separated) |
| `GATEWAY_MAX_BODY_MB` | `10` | Max request body size (MB) |
| `ENV` | `development` | Environment mode |

### CORS Configuration

```ini
# Development (default)
GATEWAY_CORS_ORIGINS=*

# Production — restrict to specific origins
GATEWAY_CORS_ORIGINS=https://myapp.com,https://admin.myapp.com
```

---

## 🧪 Testing

```powershell
# Run all gateway tests
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/gateway/ -v

# Test store layer (pure unit tests, isolated SQLite)
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/gateway/test_store.py -v

# Test routes via DI (FastAPI TestClient)
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/gateway/test_routes.py -v

# Test integration (full lifespan startup/shutdown)
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/gateway/test_integration.py -v
```

### Testing Layers

| Layer | What | How | Monkeypatch? |
|-------|------|-----|-------------|
| **Layer 1: Pure Unit** | `store.py` directly | Isolated `tmp_path` SQLite databases | No |
| **Layer 2: Route Tests** | All route modules | FastAPI `TestClient` + `app.dependency_overrides` | **Forbidden** |
| **Layer 3: Integration** | Full lifespan | Real dependency wiring, startup/shutdown | No |

**Key rule:** Route tests use `app.dependency_overrides` to inject mock stores, dispatchers, and runners. Monkeypatching is strictly forbidden — it bypasses FastAPI's DI system and produces fragile tests.

---

## 🔀 When to Use What

| Scenario | Endpoint | Why |
|----------|----------|-----|
| Submit long-running task | `POST /task` + poll `GET /result/{id}` | Non-blocking, 300s timeout |
| Quick question | `POST /chat` | Blocks until complete, simple |
| Check system health | `GET /health` | All subsystems in one response |
| Check if models loaded | `GET /health/models` | LM Studio model availability |
| Monitor circuit breakers | `GET /health/circuit-breakers` | LLM failure states |
| View recent traces | `GET /traces` | Last 10 traces from memory |
| View trace timeline | `GET /traces/{id}` | Full execution history |
| List reports | `GET /api/reports` | All reports with metadata |
| View report | `GET /reports/{id}/index.html` | Browser-viewable HTML |
| Prometheus metrics | `GET /metrics` | Node durations, task counts, tokens |
| Autocode state machine | `GET /autocode/graph` | Mermaid flowchart |

---

## ⚠️ Known Concerns

> **Note:** These are MiMo's observations from source code review. They are constructive suggestions, not definitive prescriptions.

### SQLite Connection-Per-Call

**What exists:**
`store.py` opens a new SQLite connection for every `_store_task()`, `_update_task()`, and `_get_task()` call. Each call acquires `_task_db_lock`, opens connection, executes, commits, closes.

**The concern:**
Under concurrent load (multiple `/task` submissions), this creates connection churn. Each open/close cycle has overhead, and the lock serializes all operations anyway.

**Suggestion:**
Use a single long-lived connection protected by the existing `_task_db_lock`. Since all operations are already serialized by the lock, a single connection is safe and eliminates the open/close overhead.

### ChromaDB Warmup is Non-Blocking

**What exists:**
The lifespan starts `_warmup_memory()` in a daemon thread and yields immediately. Early requests may hit cold ChromaDB.

**The concern:**
The warmup might not complete before the first real memory call arrives, defeating its purpose.

**Suggestion:**
Either block before yield (delays server start but guarantees warm ChromaDB), or add a readiness check that returns 503 until warmup completes.

### uvicorn.run() String Reference

**What exists:**
`gateway.py` does `uvicorn.run("core.gateway:create_app", ...)` but the actual factory is in `core.gateway_backend.factory`.

**The concern:**
The string reference works because the facade imports `create_app` at module level, but it's fragile — if someone removes the import, uvicorn fails with an opaque error.

**Suggestion:**
Use the actual module path: `"core.gateway_backend.factory:create_app"`.

---

## 🛡️ AI Agent Instructions

If you are an AI assistant modifying the gateway:

1. **Thin facade** — never add logic to `core/gateway.py`. All implementation belongs in `core/gateway_backend/`.
2. **One-way dependencies** — `gateway_backend` may import from `runtime`, `tools`, `workflows`. Never the reverse.
3. **No monkeypatching** — route tests must use `app.dependency_overrides`, never `unittest.mock.patch` on route internals.
4. **Pydantic contracts** — all endpoints must have `response_model`. Never return raw dicts from routes.
5. **Lazy imports in dispatcher** — tool imports must remain inside the dispatch function, not at module level.
6. **stderr only** — never use `print()` to stdout. All output goes to `sys.stderr` to keep MCP stdio clean.
7. **Auth on all routes** — every route except `/health` and `/version` must use `Depends(check_auth)`.
8. **Trace everything** — every request must have a `trace_id` (from header or generated). All exceptions must log with `trace_id`.
9. **Rate limiting** — never remove rate limiting. If slowapi is unavailable, implement a basic fallback.
10. **Security guards** — never remove the startup guard for default secret in production.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `core/gateway.py` | Thin facade — imports `create_app`, exposes `app` |
| `core/gateway_backend/factory.py` | App factory, lifespan, middleware, exception handlers |
| `core/gateway_backend/dependencies.py` | Auth (`check_auth`), DI providers |
| `core/gateway_backend/dispatcher.py` | Tool/workflow routing |
| `core/gateway_backend/exceptions.py` | `TaskNotFoundError`, `ToolExecutionError` |
| `core/gateway_backend/models.py` | Pydantic request/response schemas |
| `core/gateway_backend/store.py` | SQLite task store |
| `core/gateway_backend/routes/tasks.py` | `POST /task`, `GET /result/{id}` |
| `core/gateway_backend/routes/chat.py` | `POST /chat` |
| `core/gateway_backend/routes/health.py` | `/health`, `/health/*`, `/version`, `/tools`, `/memory/stats` |
| `core/gateway_backend/routes/metrics.py` | `/metrics`, `/autocode/graph` |
| `core/gateway_backend/routes/traces.py` | `/traces`, `/traces/{id}` |
| `core/gateway_backend/routes/reports.py` | `/reports/*`, `/logs/*`, `/api/reports` |
| `core/runtime/task_runner.py` | Background task executor |
| `core/runtime/activity_tracker.py` | Idle detection (`tracker.touch()`) |
| `core/config.py` | Gateway host, port, secret, CORS, body limit |
| `core/tracer.py` | Trace logging |
| `core/metrics.py` | Prometheus metrics |

---

## 🔮 Future Roadmap

| Status | Enhancement | Description |
|--------|-------------|-------------|
| ✅ Complete | Thin facade extraction | `core/gateway.py` → `core/gateway_backend/` |
| ✅ Complete | Pydantic contract locking | `response_model` on all endpoints |
| ✅ Complete | Centralized exception handlers | Zero try/except in routes |
| ✅ Complete | Rate limiting | slowapi integration |
| ✅ Complete | Request ID middleware | `X-Request-ID` header tracking |
| ✅ Complete | Payload size limits | MaxBodySize middleware |
| ✅ Complete | Report serving | Static files with CSP + path traversal protection |
| 🚧 Planned | WebSocket support | Real-time task progress streaming |
| 🚧 Planned | OpenAPI schema versioning | `v1/` prefix for backward compatibility |
| 🚧 Planned | API key rotation | Support multiple valid secrets for zero-downtime rotation |
| 🚧 Planned | Request logging middleware | Structured request/response logging to tracer |

---

*Last updated: June 2026. All endpoints, middleware, and security guards reflect current source code in `core/gateway.py` and `core/gateway_backend/`.*