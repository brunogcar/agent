# ⚡ Parallel Tool

The `parallel()` tool executes multiple tool calls concurrently via three action modes: `run` (barrier — wait for all), `race` (first success wins), and `pipeline` (sequential chain with result feeding). It uses a `ThreadPoolExecutor` with real global timeout enforcement and a nested-call guard.

**Key characteristics:**
- **3 actions via `@meta_tool`** — `run` (barrier via `wait()`), `race` (first success via `as_completed()`), `pipeline` (sequential, NOT parallel despite the tool name). The `action: Literal["pipeline","race","run"]` type is auto-generated from `DISPATCH`.
- **`parallel_ops/` subpackage (8 files)** — Facade is a thin `@tool @meta_tool` dispatch wrapper; all logic lives in `tools/parallel_ops/` (`_registry.py`, `__init__.py` auto-discovery, `tool_map.py`, `executor.py`, `actions/{__init__,run,race,pipeline}.py`). Auto-discovery: drop a new file in `actions/` to add a 4th action — no facade edits needed.
- **Pipeline "feed" mechanism** — Per-task `feed` key (`None` \| `str` dot-path \| `dict` of arg-name → dot-path) controls how each result flows into the next call's args. `str` replaces args entirely; `dict` merges into args.
- **Real global timeout** — `concurrent.futures.wait()` with `cfg.worker_timeout` (default 60s) for `run`; `as_completed()` for `race` (legitimate — needs completion order). Per-call `timeout` param overrides the global default.
- **Nested-call guard** — `threading.local()` (`_parallel_depth`) prevents `parallel → parallel` recursion / deadlock. All three engines increment it; pipeline stages that call `parallel()` are also blocked.
- **`PARALLEL_SAFE` allowlist (10 tools)** + **`_TOOL_MAP` (17 tools, all lazy-imported)** — Conservative safety boundary; `allow_unsafe=True` bypasses the check for `run`/`race` (ignored for `pipeline` — sequential, no hazard).
- **Backwards-compat shim** — `core/parallel_executor.py` re-exports everything from `tools.parallel_ops.*`. Existing imports continue to work.

**BREAKING v1.0:** Param `tools` renamed to `tasks`. `action` is now required. See [CHANGELOG.md](parallel/CHANGELOG.md) for migration details.

---

## 🚀 Quick Start

```python
# action="run" — Parallel web searches (barrier, wait for all)
parallel(action="run", tasks=[
    {"name": "web", "args": {"action": "search", "query": "Python 3.12 features"}},
    {"name": "web", "args": {"action": "search", "query": "Rust async patterns"}},
])

# action="race" — First successful result wins (cancel rest)
parallel(action="race", tasks=[
    {"name": "web", "args": {"action": "search", "query": "Python async patterns"}},
    {"name": "tavily", "args": {"query": "Python async patterns"}},
], allow_unsafe=True)  # tavily is NOT in PARALLEL_SAFE

# action="pipeline" — Sequential chain, feed results forward
parallel(action="pipeline", tasks=[
    {"name": "file", "args": {"action": "read", "path": "bug_report.txt"}},
    {"name": "consult", "args": {"action": "review", "question": "What's the root cause?"},
     "feed": {"context": "result.text"}},
])

# Mixed safe tools with explicit per-call timeout
parallel(action="run", tasks=[
    {"name": "web", "args": {"action": "search", "query": "ChromaDB best practices"}},
    {"name": "python", "args": {"mode": "run", "code": "print(2 + 2)"}},
    {"name": "notify", "args": {"action": "send", "message": "Research started"}},
], max_workers=8, timeout=30)
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `worker_timeout` | `cfg.worker_timeout` | 60s | Global timeout fallback for `run`/`race` when `timeout=-1`. Set `WORKER_TIMEOUT` in `.env`. Per-call `timeout` param overrides. |

---

## 🔀 When to Use vs Alternatives

| Need | Action / Tool | Why |
|------|---------------|-----|
| Multiple independent web searches | `parallel(action="run")` | Network I/O is parallelizable; barrier semantics collect all results |
| Multiple file reads | `parallel(action="run")` | Disk I/O is parallelizable |
| Mixed read-only operations | `parallel(action="run")` | No write conflicts |
| First-success-wins (primary + fallback) | `parallel(action="race")` | Cancel the loser; saves latency |
| Sequential chain with output feeding next | `parallel(action="pipeline")` | NOT parallel — ordered execution; each result fed forward |
| Multiple git commits | ❌ sequential `git` | `index.lock` collisions |
| Multiple memory writes | ❌ sequential `memory` | ChromaDB `database is locked` |
| Dependent operations (B depends on A) | `parallel(action="pipeline")` if linear, else ❌ sequential calls | Race hazards otherwise |
| Single tool call | ❌ direct call | Thread pool overhead is wasteful |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](parallel/ARCHITECTURE.md) | Source code reference (8 files in `parallel_ops/`), module tree, dispatch flow (mermaid), 3 execution engines, pipeline feed mechanism, backwards-compat shim, PARALLEL_SAFE expansion (10) + _TOOL_MAP (17), test layout (7 files, 93 tests), design decisions |
| [API.md](parallel/API.md) | Full `@meta_tool` signature with `action` + `tasks` params, 3 action sections (run/race/pipeline) with params/returns/examples, pipeline feed mechanism, PARALLEL_SAFE + _TOOL_MAP tables, error handling table, output formats |
| [CHANGELOG.md](parallel/CHANGELOG.md) | v1.0 breaking changes (`tools`→`tasks`, `action` required, `core/parallel_executor.py` shim), completed features, suggested roadmap (batch/map_reduce/dag/streaming/dynamic-safe/aggregate/cross-call/priority/retry) |
| [INSTRUCTIONS.md](parallel/INSTRUCTIONS.md) | AI editing rules — `@meta_tool` pattern, never call `dispatch_*` directly from facade, never add to `PARALLEL_SAFE` without thread-safety analysis, always use `_get_tool_fn` for lazy imports, anti-patterns |

---

*Last updated: 2026-07-15 (v1.0). See subfiles for detailed documentation.*
