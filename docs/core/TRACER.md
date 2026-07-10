# 📝 Tracer

The Tracer (`core/tracer.py` — now a **thin facade** → `core/observability/tracer_engine.py`) is the **centralized, structured logging and trace ID propagation system** for the entire agent stack. It provides end-to-end observability for workflows, tool executions, and LLM calls while strictly enforcing MCP stdio safety protocols.

> **v1.3 extraction:** The Tracer implementation moved to `core/observability/tracer_engine.py`. `core/tracer.py` is now a thin facade that re-exports `tracer`, `Tracer`, `_TraceStore`, `generate_trace_id`, `_writer` (and other module-level names) so 71+ callsites don't need to change import paths. The full observability subsystem — including `tracer_reader` (now `core/observability/reader.py`), `metrics` (now `core/observability/metrics.py`), and `checkpoint` (now `core/observability/checkpoint.py`) — is documented at [OBSERVABILITY.md](observability/OBSERVABILITY.md).

**Key characteristics:**
- **MCP stdio safety** — NEVER writes to `sys.stdout`; all output goes to stderr and JSONL files
- **Dual output** — Structured stderr (console) + JSONL files (persistent, queryable)
- **Trace ID propagation** — Every operation tagged with 8-char hex ID for end-to-end correlation
- **Bounded memory** — In-memory store capped at 200 traces with FIFO eviction
- **Thread-safe** — All writes guarded by `threading.Lock()`
- **Graceful degradation** — Falls back to standard `logging` if `structlog` is missing

---

## 🚀 Quick Start

```python
from core.tracer import tracer

# Create a trace
tid = tracer.new_trace(workflow="autocode", goal="fix memory.py import error")

# Log steps
tracer.step(tid, "read", "file loaded", chars=4200)
tracer.step(tid, "apply", "patch applied")

# Log errors
tracer.error(tid, "apply", "patch failed", error="context mismatch")

# Finish
tracer.finish(tid, success=True, result="committed abc123")
```

---

## ⚙️ Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `AUTOCODE_DEBUG` | `0` | Set to `1` for verbose DEBUG-level logs |
| `FASTMCP_LOG_LEVEL` | `error` | Suppress FastMCP internal logs |
| `LOG_PATH` | `{agent_root}/logs` | JSONL log file directory |

---

## 🔄 When to Use

| Scenario | Method | Why |
|----------|--------|-----|
| Trace a workflow | `tracer.new_trace()` + `tracer.step()` | End-to-end correlation |
| Log an error | `tracer.error()` | Captures failure context |
| Non-trace warning | `tracer.warning()` | No trace_id required |
| Query traces | `tracer.get()` / `tracer.recent()` | Fast in-memory lookup |
| Post-mortem | `tracer_reader.read_trace()` | Disk scan for old traces |
| Prometheus metrics | `core/metrics.py` | Quantitative monitoring |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](tracer/ARCHITECTURE.md) | Module tree, data flow, MCP stdio safety, trace lifecycle, observability integration, known concerns, testing (legacy v1 view — for the v1.3 extraction, see [observability/ARCHITECTURE.md](observability/ARCHITECTURE.md)) |
| [API.md](tracer/API.md) | Core methods, trace record structure, trace retrieval, structlog & fallback, CLI querying |
| [CHANGELOG.md](tracer/CHANGELOG.md) | Version history, completed milestones, roadmap |
| [INSTRUCTIONS.md](tracer/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |
| [OBSERVABILITY.md](OBSERVABILITY.md) | v1.3 canonical root for the full observability subsystem (tracer engine + reader + metrics + checkpoint) |

---

*Last updated: 2026-07-10. See subfiles for detailed documentation. (v1.3: implementation moved to core/observability/tracer_engine.py; core/tracer.py is now a facade)*
