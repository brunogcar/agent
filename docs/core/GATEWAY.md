# 🌐 Gateway

The Gateway (`core/gateway.py`) is the **HTTP edge** of the MCP Agent Stack. It exposes the agent's cognitive runtime, tools, and workflows over a REST API so external clients (second PC, phone, browser, messaging adapters) can interact with it.

**Key characteristics:**
- **Thin facade pattern** — `core/gateway.py`'s app-creation logic is one line (`app = create_app()`); all actual routing/middleware/business logic lives in `core/gateway_backend/`.
- **Async task submission** — Submit tasks, get `trace_id` immediately, poll for results
- **Synchronous chat** — Block-and-wait for quick interactions
- **Bearer token auth** — Configurable secret, hard-stop in production with default
- **Rate limiting** — 30/min on `/chat`, 60/min on `/task` via slowapi
- **Centralized error handling** — Zero try/except boilerplate in routes
- **Contract-locked responses (partial)** — Pydantic `response_model` on `/task`, `/result/{id}`, and `/chat` only

---

## 🚀 Quick Start

```bash
# Submit an async task
curl -X POST http://localhost:8000/task   -H "Authorization: Bearer $GATEWAY_SECRET"   -H "Content-Type: application/json"   -d '{"goal": "Research ChromaDB best practices", "workflow": "auto"}'

# Synchronous chat
curl -X POST http://localhost:8000/chat   -H "Authorization: Bearer $GATEWAY_SECRET"   -H "Content-Type: application/json"   -d '{"message": "What is ChromaDB?"}'

# Check health
curl http://localhost:8000/health

# Poll for result
curl -H "Authorization: Bearer $GATEWAY_SECRET"   http://localhost:8000/result/abc-123-def
```

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

## 🔄 When to Use

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

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](gateway/ARCHITECTURE.md) | Component map, request flow, domain boundaries, lifecycle, middleware, testing |
| [API.md](gateway/API.md) | Full endpoint reference, dispatcher, auth, SQLite store, error handling, Pydantic contracts |
| [CHANGELOG.md](gateway/CHANGELOG.md) | Version history, completed milestones, roadmap |
| [INSTRUCTIONS.md](gateway/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

*Last updated: 2026-07-04. See subfiles for detailed documentation.*
