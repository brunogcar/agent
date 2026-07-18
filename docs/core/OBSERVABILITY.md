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

## 🆕 v1.1 Changes (2026-07-18)

| Area | Change |
|------|--------|
| `tracer.step/error/warning` 2-arg fix | 10 callers that passed a literal string or empty string as `trace_id` now use `tracer.new_trace()` to create a unique trace_id. Prevents trace collisions in `_TraceStore` and ambiguous JSONL queries. (`warning()` confirmed to require a real `trace_id` — it is NOT a trace-free escape hatch.) |
| `reader._scan_disk()` log path | Now scans `cfg.agent_log_path` (`logs/agent/`) instead of `cfg.log_path` (`logs/`). The old non-recursive glob could never find `_FileWriter`'s files, so the disk-scan fallback was completely broken. |
| `checkpoint.sanitize_state()` `__fspath__` | Path-like objects now converted via `os.fspath()` instead of `str()`. The old `str()` call fell back to `__repr__` for objects that define `__fspath__` but not `__str__` (e.g., `os.DirEntry`). |
| Test expansion | `tests/core/tracer/` (2 files, ~10 tests) → `tests/core/observability/` (5 files, **147 tests**) with a shared `conftest.py`. Tests now patch `core.observability.tracer_engine._writer` (NOT `core.tracer._writer`). |

See [observability/CHANGELOG.md](observability/CHANGELOG.md) for the full v1.1 changelog and the per-file fix list.

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
| Trace-scoped warning | `tracer.warning()` | Non-fatal issue on an active trace (requires `trace_id` from `new_trace()`) |
| Query traces | `tracer.get()` / `tracer.recent()` | Fast in-memory lookup |
| Post-mortem | `read_trace()` | Disk scan for old traces |
| Prometheus metrics | `core.observability.metrics` | Quantitative monitoring |
| Save workflow state | `save_checkpoint()` | Crash-safe resumability |
| Resume a workflow | `get_latest()` | Restore from journal |
| Find crashed workflows | `scan_incomplete()` | Server-boot recovery |

> ⚠️ **v1.1:** `tracer.warning()` takes the same signature as `step()` — `warning(trace_id, node, message="", **kwargs)`. It requires a real `trace_id` from `new_trace()`. The old "When to Use" row claiming "No trace_id required" was incorrect and has been fixed.

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

*Last updated: 2026-07-18. See subfiles for detailed documentation.*
