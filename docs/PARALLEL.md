# Parallel Tool Execution

The `parallel` tool allows the LLM to execute multiple independent tool calls
concurrently, reducing latency for multi-step operations.

## Architecture

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────┐
│  tools/     │────▶│  core/               │────▶│  Actual     │
│  parallel.py│     │  parallel_executor.py│     │  Tools      │
│  (@tool)    │     │  (ThreadPoolExecutor)│     │  (web, git) │
└─────────────┘     └──────────────────────┘     └─────────────┘
```

- **`tools/parallel.py`** — MCP tool wrapper the LLM calls. Validates inputs,
  maps tool names to functions, enforces safety rules.
- **`core/parallel_executor.py`** — Pure execution engine. Runs calls in a
  `ThreadPoolExecutor` with configurable `max_workers`.

## Safety Model

By default, only tools in the `PARALLEL_SAFE` frozenset are eligible:

```python
PARALLEL_SAFE = frozenset({
    "web", "git", "file", "python", "python_exec",
    "notify", "memory", "memory_tool", "cli",
})
```

To override (use with caution):

```python
parallel(tools=[...], allow_unsafe=True)
```

## Usage

```python
parallel(tools=[
    {"name": "web", "args": {"action": "search", "query": "Python 3.12"}},
    {"name": "web", "args": {"action": "search", "query": "Rust async"}},
    {"name": "git", "args": {"action": "status", "root": "workspace"}},
])
```

## Return Schema

Standard `ToolResult` with `data` containing:

| Key       | Type  | Description                          |
|-----------|-------|--------------------------------------|
| results   | list  | `{"tool": str, "status": str, "result": Any}` |
| errors    | list  | `{"tool": str, "error": str}`        |
| completed | int   | Number of successful calls           |
| failed    | int   | Number of failed calls               |

## Limits

- `max_workers`: 1–8 (hard cap, default 4)
- Single call timeout: 30 seconds per tool
- Nested parallel calls are blocked (prevents recursion)
