<- Back to [Observability Overview](OBSERVABILITY.md)

# 🛠️ API Reference

## 1. Tracer (`core.observability.tracer_engine`, via `core.tracer` facade)

> **Import:** Always import the singleton via the facade — `from core.tracer import tracer`. Do NOT import directly from `core.observability.tracer_engine` in consumer code (see [INSTRUCTIONS.md](INSTRUCTIONS.md) NEVER DO rule #1).

### `tracer.new_trace(workflow: str, goal: str = "", **kwargs) -> str`

Create a new trace and return its 12-char hex trace ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workflow` | `str` | — | Workflow name (e.g., `"autocode"`, `"research"`) |
| `goal` | `str` | `""` | Human-readable goal of this trace |
| `**kwargs` | — | — | Extra fields merged into the trace record |

**Returns:** `str` — 12-char hex trace ID (e.g., `"a3f2c0b1d4e5"`).

**Side effects:** Writes a `trace_start` event to JSONL log + stderr. Stores the trace record in `_TraceStore` (in-memory, bounded to 200).

**Note on kwargs ordering:** `**kwargs` is spread FIRST so hardcoded keys (`trace_id`, `workflow`, `goal`, `started_at`, `started_fmt`, `status`, `steps`) cannot be accidentally overwritten by caller-supplied kwargs. This is a P0 fix applied consistently across all Tracer methods.

---

### `tracer.step(trace_id: str, node: str, message: str = "", **kwargs) -> None`

Log a step-level event for an active trace.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trace_id` | `str` | — | Trace ID from `new_trace()` |
| `node` | `str` | — | Node name (e.g., `"execute"`, `"read"`) |
| `message` | `str` | `""` | Human-readable message |
| `**kwargs` | — | — | Extra fields (e.g., `chars=4200`, `latency_ms=12.5`) |

**Side effects:** Appends to trace's `steps` list in `_TraceStore`. Writes a `step` event to JSONL log. If `cfg.autocode_debug`, also logs to stderr via structlog.

> ⚠️ **v1.1 — `trace_id` must come from `new_trace()`.** NEVER pass a literal string or empty string as `trace_id` (e.g., `tracer.step("health", ...)` or `tracer.step("", "node", ...)`). The signature is `step(trace_id, node, message="")`, so a 2-arg call silently sets `trace_id` to your literal and `node` to your message — this causes trace collisions in the in-memory `_TraceStore` and makes JSONL log queries ambiguous. Always call `tracer.new_trace()` first and pass the returned ID. See [INSTRUCTIONS.md](INSTRUCTIONS.md) NEVER DO #15 and Anti-Pattern 6.

---

### `tracer.error(trace_id: str, node: str, message: str = "", **kwargs) -> None`

Log an error event for an active trace. Same signature as `step()`.

**Side effects:** Appends to trace's `steps` list. Writes an `error` event to JSONL log + stderr.

> ⚠️ **v1.1** — same `trace_id` requirement as `step()`: must come from `new_trace()`, never a literal/empty string.

---

### `tracer.warning(trace_id: str, node: str, message: str = "", **kwargs) -> None`

Log a warning-level event. Same signature as `step()`. Useful for non-fatal issues (e.g., "Checkpoint version mismatch, starting fresh").

> ⚠️ **v1.1** — `warning()` requires a real `trace_id` from `new_trace()`, just like `step()`/`error()`. It is NOT a trace-free logging escape hatch. For trace-scoped warnings, call `new_trace()` first.

---

### `tracer.finish(trace_id: str, success: bool = True, result: str = "", **kwargs) -> None`

Mark a trace as complete.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trace_id` | `str` | — | Trace ID |
| `success` | `bool` | `True` | Whether the trace succeeded |
| `result` | `str` | `""` | Final result summary (truncated to 200 chars) |
| `**kwargs` | — | — | Extra fields merged into the finish event |

**Side effects:** Updates trace status to `"success"` or `"failed"`. Computes elapsed seconds from `started_at`. Appends a `trace_finish` event. Writes to JSONL log + stderr.

---

### `tracer.get(trace_id: str) -> Optional[dict]`

Retrieve the in-memory trace record by ID. Returns `None` if not in the bounded store (e.g., evicted or never created).

---

### `tracer.recent(n: int = 10) -> list[dict]`

List the N most recent traces (newest first). Default is 10. Reads from in-memory store only — does not scan disk.

---

### `tracer.summary(trace_id: str) -> str`

Return a one-line summary string for a trace. Example: `"[a3f2c0b1] autocode | goal='fix bug' | status=success | steps=5 | elapsed=2.4s"`. Returns `"trace {trace_id} not found"` if not in memory.

---

### `generate_trace_id(length: int = 12) -> str`

Generate a short hex trace ID. Default length is 12 chars (was 8 in early versions). Uses `uuid.uuid4().hex[:length]`.

---

## 2. Reader (`core.observability.reader`)

> **Import:** `from core.observability.reader import read_trace, list_recent_traces` (direct import — no facade for the reader).

### `read_trace(trace_id: str) -> Optional[dict]`

Retrieve a full trace timeline by `trace_id`. Two-path strategy:

1. **Fast path:** Check in-memory `_TraceStore` (holds last 200 traces). If found, return formatted timeline.
2. **Slow path:** Scan JSONL log files in `cfg.agent_log_path` (newest first, limited to last 14 days). Parse each line, filter by `trace_id`, collect `trace_start`/`trace_finish` metadata and `step`/`error`/`warning` events.

**Returns:** `dict` with `trace_id`, `workflow`, `goal`, `status`, `started_at`, `elapsed_s`, `result`, `steps` — or `None` if not found in memory or on disk.

**Returns `None` for:** empty `trace_id`, missing log dir, no matching records.

> ✅ **v1.1 fix:** The slow path previously scanned `cfg.log_path` (`logs/`) but `_FileWriter` writes to `cfg.agent_log_path` (`logs/agent/`). The non-recursive `glob("agent_*.jsonl")` could never find the writer's files, so the disk-scan fallback was completely broken. It now scans `cfg.agent_log_path`.

---

### `list_recent_traces(limit: int = 10) -> list[dict]`

List recent traces from in-memory store. Returns up to `limit` formatted trace dicts (newest first). Does NOT scan disk.

**Returns:** list of dicts, each with `trace_id`, `workflow`, `goal`, `status`, `started_at`, `elapsed_s`, `result`, `steps`.

---

## 3. Metrics (`core.observability.metrics`)

> **Import:** `from core.observability.metrics import track_node, track_task_status, track_tdd_iterations, track_llm_tokens, generate_metrics, get_content_type` (direct import).

All `track_*` functions are safe to call from anywhere — they become no-ops when `prometheus_client` is not installed.

### `track_node(node_name: str, duration: float) -> None`

Observe a node execution duration (seconds) on the `autocode_node_duration_seconds` histogram (label: `node_name`).

### `track_task_status(status: str) -> None`

Increment the `autocode_task_status_total` counter (label: `status`). Call with terminal statuses like `"success"`, `"failed"`, `"cancelled"`.

### `track_tdd_iterations(count: int) -> None`

Observe the number of TDD iterations for a task on the `autocode_tdd_iterations` histogram.

### `track_llm_tokens(role: str, prompt: int, completion: int) -> None`

Increment the `autocode_llm_tokens_total` counter (label: `role`) by `prompt + completion`.

### `generate_metrics() -> str`

Return the Prometheus text-format exposition string for all registered metrics. If `prometheus_client` is missing, returns a placeholder comment.

### `get_content_type() -> str`

Return the appropriate HTTP `Content-Type` header value (`CONTENT_TYPE_LATEST` from prometheus_client, or `"text/plain"` as fallback).

---

## 4. Checkpoint (`core.observability.checkpoint`)

> **Import:** `from core.observability.checkpoint import save_checkpoint, get_latest, mark_complete, scan_incomplete, quarantine, sanitize_state` (direct import).

### `save_checkpoint(trace_id: str, node_name: str, state: dict) -> None`

Append a checkpoint entry to `checkpoints/{trace_id}.jsonl`. No-op if `trace_id` is falsy.

**Entry shape:**
```json
{
  "ts": 1720000000.0,
  "node": "execute",
  "status": "running",
  "state": { /* sanitized state */ },
  "resume_count": 0,
  "version": 1
}
```

**Side effects:** Counts existing `"resume"` entries to set `resume_count`. Calls `f.flush()` + `os.fsync(f.fileno())` after write. Non-fatal I/O errors are logged via `logger.warning` and swallowed.

---

### `get_latest(trace_id: str) -> Optional[dict]`

Read the last checkpoint entry for a trace. Returns the `state` dict, or `None` if:
- No journal file exists
- Journal is empty
- Trace is detected as a zombie (quarantined)

**Zombie detection triggers quarantine:**
1. `resume_count >= MAX_RESUMES (5)` — too many resume attempts
2. Consecutive same-node failures (`prev.status == failed && entry.status == failed && prev.node == entry.node && prev.node not in ("resume", "")`)

**Version injection:** If `state` is a dict, injects `_checkpoint_version` from the envelope so consumers can validate compatibility.

---

### `mark_complete(trace_id: str) -> None`

Delete the checkpoint journal on successful completion. No-op if file doesn't exist or deletion fails.

---

### `scan_incomplete() -> list[str]`

Find all incomplete workflows. Scans `checkpoints/*.jsonl` modified in the last 48 hours; returns the trace IDs (filename stems) whose last entry's `status` is not `"success"` or `"failed"`.

**Returns:** list of trace ID strings. Empty list if none incomplete or all journals are older than 48h.

---

### `quarantine(trace_id: str) -> None`

Move a workflow journal from `checkpoints/` to `checkpoints/quarantine/`. Called automatically by `get_latest()` on zombie detection. Can also be called manually to isolate a misbehaving workflow.

---

### `sanitize_state(state: Any, _seen: set = None) -> Any`

Recursively extract JSON-safe primitives from a state object. Used by `save_checkpoint()` before serializing.

**Supported types:** `str`, `int`, `float`, `bool`, `None`, `datetime.{datetime,date,time}` (→ ISO format), `datetime.timedelta` (→ seconds), `bytes` (→ UTF-8 decoded), `Decimal` (→ str), `uuid.UUID` (→ str), `Path`-like (→ str via `os.fspath()`), `dict` (recursive), `list`/`tuple` (recursive), `set` (sorted-then-recursive if sortable, else unsorted).

**Dropped types:** Any other object (httpx clients, locks, CircuitBreakers) → `None`. Prevents `json.dumps()` crashes on unserializable workflow state.

**Circular reference handling:** Tracks `id()` of containers (dict/list/tuple/set) in `_seen`. Returns `"<circular_reference>"` if a container is revisited. Does NOT track primitives (they're interned in CPython and would false-positive).

> ✅ **v1.1 fix:** Path-like objects are now converted via `os.fspath(state)` instead of `str(state)`. The old `str()` call fell back to `__repr__` for objects that define `__fspath__` but not `__str__` (e.g., `os.DirEntry`), producing repr garbage instead of the path string. `os.fspath()` correctly invokes `__fspath__()`.

---

## 5. Module-Level Constants

| Constant | Module | Description |
|----------|--------|-------------|
| `CHECKPOINT_DIR` | `checkpoint.py` | `cfg.workspace_root / "checkpoints"` — created at import time |
| `QUARANTINE_DIR` | `checkpoint.py` | `CHECKPOINT_DIR / "quarantine"` — created at import time |
| `MAX_RESUMES` | `checkpoint.py` | `5` — hard cap on resume attempts before zombie quarantine |
| `_HAS_STRUCTLOG` | `tracer_engine.py` | `True` if `structlog` is importable, else `False` (falls back to stdlib `logging`) |
| `_PROM_AVAILABLE` | `metrics.py` | `True` if `prometheus_client` is importable, else `False` (all `track_*` become no-ops) |
| `registry` | `metrics.py` | `CollectorRegistry()` singleton if Prometheus available, else `None` |
| `_TraceStore.MAX_TRACES` | `tracer_engine.py` | `200` — in-memory store bound; FIFO eviction when exceeded |

---

*Last updated: 2026-07-18. See [ARCHITECTURE.md](ARCHITECTURE.md) for module layout, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
