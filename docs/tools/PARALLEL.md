# ⚡ Parallel Tool

The `parallel()` tool executes multiple independent tool calls concurrently, reducing latency for multi-step operations. It uses a `ThreadPoolExecutor` with real global timeout enforcement and nested-call protection.

**Key characteristics:**
- **Concurrent execution** — Multiple tool calls run in parallel via `ThreadPoolExecutor`
- **Real global timeout** — `concurrent.futures.wait()` with `cfg.worker_timeout` (default 60s), not broken `as_completed()` per-future timeout
- **Nested-call guard** — `threading.local()` prevents `parallel → parallel` recursion / deadlock
- **Safety-first** — Conservative `PARALLEL_SAFE` allowlist; write-heavy tools excluded
- **Explicit mapping** — `_TOOL_MAP` imports tool functions directly; no runtime discovery

---

## 🚀 Quick Start

```python
# Parallel web searches
parallel(tools=[
    {"name": "web", "args": {"action": "search", "query": "Python 3.12 features"}},
    {"name": "web", "args": {"action": "search", "query": "Rust async patterns"}},
])

# Parallel file reads
parallel(tools=[
    {"name": "file", "args": {"action": "read", "path": "config.yaml"}},
    {"name": "file", "args": {"action": "read", "path": "README.md"}},
])

# Mixed safe tools
parallel(tools=[
    {"name": "web", "args": {"action": "search", "query": "ChromaDB best practices"}},
    {"name": "python", "args": {"mode": "run", "code": "print(2 + 2)"}},
    {"name": "notify", "args": {"action": "send", "message": "Research started"}},
])
```

---

## ⚙️ Configuration

| Config | Source | Default | Description |
|--------|--------|---------|-------------|
| `worker_timeout` | `cfg.worker_timeout` | 60s | Global timeout for parallel execution. Set `WORKER_TIMEOUT` in `.env`. |

---

## 🔀 When to Use vs Alternatives

| Need | Tool | Why |
|------|------|-----|
| Multiple independent web searches | `parallel` | Network I/O is parallelizable |
| Multiple file reads | `parallel` | Disk I/O is parallelizable |
| Mixed read-only operations | `parallel` | No write conflicts |
| Multiple git commits | ❌ sequential `git` | `index.lock` collisions |
| Multiple memory writes | ❌ sequential `memory` | ChromaDB `database is locked` |
| Dependent operations (B depends on A) | ❌ sequential calls | Parallel would race |
| Single tool call | ❌ direct call | Thread pool overhead is wasteful |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](parallel/ARCHITECTURE.md) | Module tree, dispatch flow, design decisions, test coverage, source code reference |
| [API.md](parallel/API.md) | Full tool signature, tool spec format, safety model, timeout, output format |
| [CHANGELOG.md](parallel/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](parallel/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-03. See subfiles for detailed documentation.*
