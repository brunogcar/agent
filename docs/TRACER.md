# 📝 Tracer Architecture & Observability Guide

The Tracer (`core/tracer.py`) is the centralized, structured logging and trace ID propagation system for the entire agent stack. It provides end-to-end observability for workflows, tool executions, and LLM calls while strictly enforcing MCP stdio safety protocols.

## 🏗️ Architecture Overview

### Design Goals

1. **MCP Stdio Safety (CRITICAL)**: NEVER writes to `sys.stdout`. In MCP stdio transport mode, stdout is the JSON-RPC protocol channel. Any non-JSON-RPC bytes on stdout corrupt the connection and crash the server.
2. **Dual Output**: All logs go to `sys.stderr` (for console/structlog output) and `logs/agent_YYYYMMDD.jsonl` (for persistent, queryable file storage).
3. **Trace ID Propagation**: Every workflow, tool call, and LLM interaction is tagged with a short hex `trace_id` (e.g., `a3f2c0b1`) for end-to-end correlation.
4. **Graceful Degradation**: If `structlog` is missing from the environment, the tracer falls back to standard library `logging` without crashing the agent.
5. **Bounded Memory**: In-memory trace storage is capped to prevent memory leaks during long-running sessions.

### Component Hierarchy

```
Tracer (singleton)
├── Trace ID Generator (uuid4 hex, 8 chars)
├── Structlog Config (stderr only, JSON renderer)
│   └── Graceful Fallback (standard logging if structlog missing)
├── _FileWriter (Thread-safe JSONL, daily rotation)
└── _TraceStore (In-memory, bounded to 200 traces)
```

---

## 🚨 MCP Stdio Safety (The Golden Rule)

**NEVER use `print()` or write to `sys.stdout` anywhere in `server.py`, `tools/`, `workflows/`, or `core/`.** 

The MCP protocol uses stdout exclusively for JSON-RPC communication between the agent and the host (LM Studio, Claude Desktop, Cursor). If any module accidentally prints to stdout, the host will receive malformed JSON and immediately terminate the connection.

**Correct Pattern:**
```python
# ❌ WRONG - Will crash MCP connection
print("Processing file...")

# ✅ RIGHT - Goes to stderr and log file
tracer.step(trace_id, "file_ops", "Processing file...", chars=4200)
```

---

## 📤 Output Destinations

### 1. Standard Error (`sys.stderr`)
- **With structlog**: Outputs structured JSON logs with timestamps, log levels, and context variables.
- **Without structlog**: Outputs formatted plain text logs (`[step] trace_id | node | message`).
- **Visibility**: Visible in the terminal when running `python server.py` or in the MCP host's debug console.

### 2. JSONL File (`logs/agent_YYYYMMDD.jsonl`)
- **Format**: One JSON object per line, easily queryable with `jq` or Python.
- **Rotation**: Automatically creates a new file at midnight (based on `YYYYMMDD`).
- **Persistence**: Survives server restarts; essential for post-mortem debugging.
- **Thread-Safety**: All writes are guarded by a `threading.Lock()` to prevent interleaved JSON.

**Example JSONL Entry:**
```json
{
  "event": "step",
  "trace_id": "a3f2c0b1",
  "node": "memory_recall",
  "message": "Querying ChromaDB",
  "ts": 1716825600.123,
  "latency_ms": 45.2,
  "original": "how to fix syntax errors",
  "rewritten": "fix syntax error"
}
```

---

## 🔄 Trace Lifecycle

Every significant operation (workflow, tool execution, gateway task) follows this lifecycle:

### 1. Create Trace (`new_trace`)
Generates a unique 8-character hex ID and initializes the trace record.

```python
from core.tracer import tracer

tid = tracer.new_trace(
    workflow="autocode",
    goal="fix memory.py import error"
)
# Returns: "a3f2c0b1"
```

### 2. Log Steps (`step`)
Records intermediate progress, tool calls, and LLM interactions.

```python
tracer.step(
    tid, 
    "read", 
    "file loaded", 
    chars=4200,
    latency_ms=12.5
)
```

### 3. Log Errors (`error`)
Records failures without crashing the trace. Marks the trace as degraded.

```python
tracer.error(
    tid, 
    "apply", 
    "patch failed", 
    error="context mismatch"
)
```

### 4. Finish Trace (`finish`)
Calculates total elapsed time, marks terminal status, and emits the final summary.

```python
tracer.finish(
    tid, 
    success=True, 
    result="committed abc123"
)
```

---

## 🧠 In-Memory Trace Store (`_TraceStore`)

The tracer maintains an in-memory dictionary of active/recent traces for quick retrieval via the REST API (`/traces` endpoint) or internal debugging.

### Bounded Capacity
- **MAX_TRACES = 200**: Prevents unbounded memory growth during long sessions.
- **FIFO Eviction**: When the limit is reached, the oldest trace is silently dropped.
- **Thread-Safe**: All reads/writes are guarded by a lock.

### Retrieval Methods

```python
# Get full trace record
trace = tracer.get(tid)
# {
#     "trace_id": "a3f2c0b1",
#     "workflow": "autocode",
#     "goal": "fix memory.py",
#     "started_at": 1716825600.0,
#     "status": "success",
#     "elapsed": 45.2,
#     "steps": [...]
# }

# Get last 10 traces (for /traces endpoint)
recent = tracer.recent(n=10)

# Get human-readable summary
summary = tracer.summary(tid)
# "[a3f2c0b1] autocode | goal='fix memory.py' | status=success | steps=12 | elapsed=45.2s"
```

---

## 📂 Thread-Safe File Writer (`_FileWriter`)

The `_FileWriter` class handles all disk I/O for the JSONL logs.

### Key Features
- **Daily Rotation**: Checks the current date on every write. If the date has changed, closes the old file and opens a new one (`agent_YYYYMMDD.jsonl`).
- **Auto-Flush**: Calls `f.flush()` after every write to ensure logs are persisted immediately (critical for crash recovery).
- **Silent I/O Errors**: Non-fatal disk errors (e.g., temporary permission issues) are silently ignored to prevent logging failures from crashing the agent.
- **Shutdown Signals**: `KeyboardInterrupt` and `SystemExit` are **never** suppressed, ensuring clean shutdowns.

---

## 🔌 Structlog & Graceful Fallback

The tracer attempts to use `structlog` for rich, structured JSON logging to stderr. However, `structlog` is treated as an **optional dependency** to ensure the agent can run in minimal environments.

### The Fallback Pattern

```python
try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False
    import logging
    logging.basicConfig(
        level=logging.DEBUG if cfg.autocode_debug else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
```

### Behavior

| Condition | stderr Output | File Output |
|-----------|---------------|-------------|
| **structlog installed** | Structured JSON with contextvars, timestamps, log levels | JSONL (always) |
| **structlog missing** | Plain text `[step] trace_id \| node \| message` | JSONL (always) |

**Why this matters**: If a user clones the repo and forgets to `pip install structlog`, the agent will still boot and log correctly using the standard library. This prevents "missing module" crashes from breaking core observability.

---

## 📡 API Reference

### `generate_trace_id(length: int = 8) -> str`
Generates a short hex trace ID from `uuid4`.

```python
tid = generate_trace_id()  # "a3f2c0b1"
```

### `tracer.new_trace(workflow: str, goal: str = "", **kwargs) -> str`
Creates a new trace, logs the start event, and returns the `trace_id`.

### `tracer.step(trace_id: str, node: str, message: str = "", **kwargs)`
Logs an intermediate step. Automatically captures timestamp and appends to the trace's `steps` list.

### `tracer.error(trace_id: str, node: str, message: str = "", **kwargs)`
Logs an error event. Does **not** mark the trace as failed (use `finish(success=False)` for that).

### `tracer.finish(trace_id: str, success: bool = True, result: str = "", **kwargs)`
Marks the trace as complete, calculates elapsed time, and logs the final event.

### `tracer.get(trace_id: str) -> Optional[dict]`
Retrieves the full in-memory trace record.

### `tracer.recent(n: int = 10) -> list[dict]`
Returns the `n` most recent traces (newest first).

### `tracer.summary(trace_id: str) -> str`
Returns a one-line human-readable summary of the trace.

---

## ⚙️ Configuration (`.env`)

```ini
# ── Debug & Logging ────────────────────────────────────────────────────────
AUTOCODE_DEBUG=0                # Set to 1 for verbose DEBUG-level logs
FASTMCP_LOG_LEVEL=error         # Suppress FastMCP internal logs
```

**Log Levels**:
- When `AUTOCODE_DEBUG=1`: structlog filters at level 10 (DEBUG), standard logging at DEBUG.
- When `AUTOCODE_DEBUG=0`: structlog filters at level 20 (INFO), standard logging at INFO.

---

## ⚠️ AI Agent Instructions for Tracer Operations

If you are an AI assistant modifying `core/tracer.py` or any file that uses it:

1. **NEVER Write to stdout**: This is the single most important rule. Any `print()` statement without `file=sys.stderr` will break the MCP connection. Always use `tracer.step()`, `tracer.error()`, or `print(..., file=sys.stderr)`.

2. **Preserve the Fallback**: Never remove the `try/except ImportError` block for `structlog`. The graceful fallback to standard `logging` is critical for environment resilience.

3. **Thread Safety**: Never remove the `_lock` from `_FileWriter` or `_TraceStore`. Concurrent workflow executions will corrupt the JSONL file or cause race conditions in the in-memory store.

4. **Bounded Memory**: Never increase `MAX_TRACES` significantly above 200 without considering memory implications. The agent may run for days; unbounded trace storage will cause OOM (Out of Memory) crashes.

5. **Silent I/O Errors**: The `_FileWriter` intentionally ignores non-fatal disk errors. Do not "fix" this by raising exceptions — a logging failure should never crash the agent.

6. **Trace ID Format**: Keep trace IDs short (8 chars). Long UUIDs bloat the JSONL logs and make terminal output hard to read.

7. **Shutdown Signals**: Never catch `KeyboardInterrupt` or `SystemExit` in the `_FileWriter`. The agent must be able to shut down cleanly when the user presses Ctrl+C.

8. **Context Variables**: When adding new log fields, use `**kwargs` in `step()`/`error()`. These are automatically merged into the JSONL record.

9. **Daily Rotation**: The `_FileWriter` checks the date on every write. Do not cache the file handle across midnight boundaries without checking `self._current_date`.

10. **No Hardcoded Paths**: The log directory is always `cfg.log_path` (default `logs/`). Never hardcode `"logs/"` in the tracer.

---

## 🔍 Querying Logs

### With `jq` (Command Line)
```bash
# Find all errors from today
cat logs/agent_20260527.jsonl | jq 'select(.event == "error")'

# Find all steps for a specific trace
cat logs/agent_20260527.jsonl | jq 'select(.trace_id == "a3f2c0b1")'

# Count steps per workflow
cat logs/agent_20260527.jsonl | jq -r '.workflow' | sort | uniq -c
```

### With Python
```python
import json
from pathlib import Path

log_file = Path("logs/agent_20260527.jsonl")
for line in log_file.read_text().splitlines():
    record = json.loads(line)
    if record.get("event") == "error":
        print(f"[{record['trace_id']}] {record['node']}: {record['message']}")
```

---

## 🔮 Future Enhancements (Planned)

- **OpenTelemetry Integration**: Export traces to Jaeger/Zipkin for distributed tracing across multiple agent instances.
- **Log Compression**: Automatically gzip old JSONL files after 7 days to save disk space.
- **Remote Log Shipping**: Optional forwarding to a centralized log aggregator (e.g., Loki, ELK) for multi-machine deployments.
- **Trace Sampling**: Automatically drop low-importance traces (e.g., simple router calls) to reduce log volume.

---

*Last updated: Phase 4 complete. Structlog fallback implemented, MCP stdio safety enforced, bounded memory active.*