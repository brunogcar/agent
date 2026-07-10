# 🔭 Observability

The Observability subsystem (`core/observability/`) is the **centralized, structured logging, tracing, metrics, and checkpoint journal** layer for the entire agent stack. It provides end-to-end visibility for workflows, tool executions, and LLM calls while strictly enforcing MCP stdio safety protocols and crash-safe workflow resumability.

**Key characteristics:**
- **MCP stdio safety** — Tracer NEVER writes to `sys.stdout`; all output goes to stderr and JSONL files
- **Dual output** — Structured stderr (console) + JSONL files (persistent, queryable)
- **Trace ID propagation** — Every operation tagged with 12-char hex ID for end-to-end correlation
- **Bounded memory** — In-memory trace store capped at 200 traces with FIFO eviction
- **Thread-safe** — All writes guarded by `threading.Lock()`
- **Graceful degradation** — Falls back to standard `logging` if `structlog` is missing; Prometheus metrics become no-ops if `prometheus_client` is missing
- **Crash-safe checkpoint journal** — Append-only JSONL per workflow, with zombie detection and quarantine
- **Thin facade pattern** — `core/tracer.py` is a re-export facade so 71+ callers don't need to change import paths

---

## 🚀 Quick Start

```python
# Tracer — use the facade (71+ files import from this path)
from core.tracer import tracer

tid = tracer.new_trace(workflow="autocode", goal="fix memory.py import error")
tracer.step(tid, "read", "file loaded", chars=4200)
tracer.error(tid, "apply", "patch failed", error="context mismatch")
tracer.finish(tid, success=True, result="committed abc123")

# Trace reader — direct import from observability
from core.observability.reader import read_trace, list_recent_traces
trace = read_trace(tid)
recent = list_recent_traces(limit=10)

# Metrics — direct import from observability
from core.observability.metrics import track_node, generate_metrics
track_node("node_run_tests", duration=2.4)
print(generate_metrics())  # Prometheus text format

# Checkpoint — direct import from observability
from core.observability.checkpoint import save_checkpoint, get_latest, mark_complete, scan_incomplete
save_checkpoint(tid, "execute", state_dict)
restored = get_latest(tid)
mark_complete(tid)
incomplete = scan_incomplete()
```

---

## ⚙️ Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `AUTOCODE_DEBUG` | `0` | Set to `1` for verbose DEBUG-level logs in tracer |
| `FASTMCP_LOG_LEVEL` | `error` | Suppress FastMCP internal logs |
| `LOG_PATH` | `{agent_root}/logs` | JSONL log file directory |
| `WORKSPACE_ROOT` | `{agent_root}/workspace` | Checkpoint journal directory root |

---

## 🔄 When to Use

| Scenario | Method | Why |
|----------|--------|-----|
| Trace a workflow | `tracer.new_trace()` + `tracer.step()` | End-to-end correlation |
| Log an error | `tracer.error()` | Captures failure context |
| Non-trace warning | `tracer.warning()` | No trace_id required |
| Query traces | `tracer.get()` / `tracer.recent()` | Fast in-memory lookup |
| Post-mortem | `read_trace()` | Disk scan for old traces |
| Prometheus metrics | `core.observability.metrics` | Quantitative monitoring |
| Save workflow state | `save_checkpoint()` | Crash-safe resumability |
| Resume a workflow | `get_latest()` | Restore from journal |
| Find crashed workflows | `scan_incomplete()` | Server-boot recovery |

---

## 📂 Subfile Directory

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](observability/ARCHITECTURE.md) | Source code reference, module tree, design decisions (facade pattern, JSONL logging, checkpoint journal, Prometheus metrics) |
| [API.md](observability/API.md) | API reference for tracer, reader, metrics, and checkpoint functions |
| [CHANGELOG.md](observability/CHANGELOG.md) | Version history, completed milestones, roadmap |
| [INSTRUCTIONS.md](observability/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

> **Note:** The Tracer subsystem has *two* documentation roots. The legacy `docs/core/tracer/` covers the original v1 file layout (now a facade). This `docs/core/observability/` is the canonical v1.3 root for the full subsystem (tracer engine + reader + metrics + checkpoint).

---

*Last updated: 2026-07-10. See subfiles for detailed documentation.*
