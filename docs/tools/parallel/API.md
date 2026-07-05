<- Back to [Parallel Overview](../PARALLEL.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
def parallel(
    tools: list[dict],
    max_workers: int = 4,
    allow_unsafe: bool = False,
    trace_id: str = "",
) -> dict:
    """Execute multiple tool calls in parallel.

    Args:
        tools: List of tool call specs. Each spec is a dict with:
            - name: str — tool name
            - args: dict — arguments to pass
        max_workers: Max concurrent threads (1-8, default 4)
        allow_unsafe: If True, allow tools not in PARALLEL_SAFE
        trace_id: Trace ID for observability

    Returns:
        ToolResult with data containing results and errors.
    """
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tools` | `list[dict]` | **Yes** | Each dict: `{"name": "tool_name", "args": {...}}`. Minimum 1 item. |
| `max_workers` | `int` | No | Thread pool size. Clamped to 1–8. Default: 4. |
| `allow_unsafe` | `bool` | No | If `True`, bypass `PARALLEL_SAFE` check. Default: `False`. |
| `trace_id` | `str` | No | Trace identifier for logging and result correlation. |

---

## ⚡ Tool Spec Format

```python
{"name": "web", "args": {"action": "search", "query": "..."}}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | `str` | **Yes** | Tool name. Must exist in `_TOOL_MAP`. |
| `args` | `dict` | No | Keyword arguments passed to the tool function. Default: `{}`. |

---

## 🔒 Security

### PARALLEL_SAFE Allowlist

```python
PARALLEL_SAFE = frozenset({
    "web",           # Network I/O — safe
    "file",          # Read ops — safe (write ops have internal locks)
    "python",        # Sandboxed execution — safe
    "python_exec",   # Alias for python — safe
    "notify",        # Desktop notification — safe
})
```

**Excluded tools (and why):**

| Tool | Reason |
|------|--------|
| `git` | Write ops (`commit`, `push`) cause `index.lock` collisions |
| `memory` | ChromaDB concurrent writes risk `database is locked` |
| `cli` | Shell commands may conflict (e.g., two `mkdir` on same path) |

### _TOOL_MAP (All Registered Tools)

| Name | Maps To | In PARALLEL_SAFE? |
|------|---------|-------------------|
| `web` | `tools.web.web` | ✅ Yes |
| `git` | `tools.git.git` | ❌ No |
| `file` | `tools.file.file` | ✅ Yes |
| `python` | `tools.python.python` | ✅ Yes |
| `python_exec` | `tools.python.python` (alias) | ✅ Yes |
| `notify` | `tools.notify.notify` | ✅ Yes |
| `memory` | `tools.memory.memory` | ❌ No |
| `memory` | `tools.memory.memory` | ❌ No |
| `cli` | `tools.cli.cli` | ❌ No |

### Override (Use with Caution)

```python
parallel(tools=[...], allow_unsafe=True)
```

This bypasses the `PARALLEL_SAFE` check. **Only use if you understand the risks** (e.g., all calls are read-only, or tools have internal locking).

---

## ⏱️ Timeout Enforcement

The executor uses `concurrent.futures.wait()` with a **global timeout** from `cfg.worker_timeout`:

```python
timeout = cfg.worker_timeout  # Default: 60s (from .env WORKER_TIMEOUT)
done, not_done = concurrent.futures.wait(futures, timeout=timeout)

for future in done:
    # Collect results

for future in not_done:
    # Mark as "Timed out after {timeout} seconds"
```

**Why `wait()` instead of `as_completed()`?** The previous implementation used `as_completed()` + `future.result(timeout=30)`, which is broken: `as_completed()` blocks indefinitely waiting for a future to finish, so the per-future timeout never fires if the future hangs. `wait()` enforces a true global deadline.

**Configurable:** Set `WORKER_TIMEOUT` in `.env` to adjust the global timeout. Default is 60 seconds.

**Note:** `ThreadPoolExecutor` cannot forcefully kill a hung thread. Timed-out threads remain orphaned until their internal timeout (e.g., `httpx` timeout, `subprocess` timeout) fires. This is acceptable for I/O-bound tools with their own timeouts.

---

## 🔄 Nested-Call Guard

The executor uses `threading.local()` to track recursion depth:

```python
_parallel_depth = threading.local()

def dispatch_parallel(...):
    if getattr(_parallel_depth, "value", 0) > 0:
        return fail("Nested parallel calls are not allowed", trace_id=trace_id)

    _parallel_depth.value = getattr(_parallel_depth, "value", 0) + 1
    try:
        # Execute calls
    finally:
        _parallel_depth.value -= 1
```

**Why?** If the LLM calls `parallel` inside `parallel`, it creates a deadlock: the outer call waits for the inner call, which waits for the outer call's thread pool. The guard prevents this with a clear error message.

---

## 📤 Output

All responses are `ToolResult` dicts from `core.contracts`:

### Success
```json
{
  "status": "success",
  "trace_id": "abc123",
  "data": {
    "results": [
      {
        "tool": "web",
        "status": "success",
        "result": {"status": "success", "data": "..."}
      },
      {
        "tool": "python",
        "status": "success",
        "result": {"status": "success", "data": "4"}
      }
    ],
    "errors": [
      {
        "tool": "file",
        "error": "FileNotFoundError: config.yaml not found"
      }
    ],
    "completed": 2,
    "failed": 1
  }
}
```

### Validation Error (from facade)
```json
{
  "status": "error",
  "trace_id": "",
  "error": "Tool 'git' is not parallel-safe. Set allow_unsafe=True to override."
}
```

### Nested Call Error (from executor)
```json
{
  "status": "error",
  "trace_id": "abc123",
  "error": "Nested parallel calls are not allowed"
}
```

### Timeout Error (from executor)
```json
{
  "status": "success",
  "trace_id": "abc123",
  "data": {
    "results": [],
    "errors": [
      {"tool": "web", "error": "Timed out after 60 seconds"}
    ],
    "completed": 0,
    "failed": 1
  }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `results` | `list` | Successful calls: `{"tool": str, "status": str, "result": Any}` |
| `errors` | `list` | Failed calls: `{"tool": str, "error": str}` |
| `completed` | `int` | Number of successful calls |
| `failed` | `int` | Number of failed calls (including timeouts) |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
