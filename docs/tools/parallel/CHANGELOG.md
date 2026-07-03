<- Back to [Parallel Overview](../PARALLEL.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| pre-v1 | — | Initial parallel tool: ThreadPoolExecutor, real global timeout, nested-call guard, PARALLEL_SAFE allowlist |

---

## ⚠️ Breaking Changes

*(No breaking changes recorded for pre-v1. Add here as they occur.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| ThreadPoolExecutor concurrent execution | ✅ pre-v1 | `dispatch_parallel` in `core/parallel_executor.py` |
| Real global timeout via `wait()` | ✅ pre-v1 | Replaced broken `as_completed()` + `future.result()` pattern |
| Nested-call guard | ✅ pre-v1 | `threading.local()` depth tracking |
| `PARALLEL_SAFE` allowlist | ✅ pre-v1 | 5 tools: `web`, `file`, `python`, `python_exec`, `notify` |
| `allow_unsafe` override | ✅ pre-v1 | Bypass safety check with explicit flag |
| `max_workers` clamp (1–8) | ✅ pre-v1 | Prevents thread pool exhaustion |
| Explicit `_TOOL_MAP` | ✅ pre-v1 | 8 tools + 2 aliases, no runtime discovery |
| Result/error wrapping | ✅ pre-v1 | `{"tool": name, "status": ..., "result": ...}` per call |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `@meta_tool` refactor | Add `action` param for sub-commands if tool grows beyond simple dispatch | P1 |
| Test restructure | Add `conftest.py`, split `test_parallel.py` into facade vs executor test files | P1 |
| Per-tool timeout configuration | `timeout={"web": 10, "python": 60}` override global `cfg.worker_timeout` | P2 |
| Streaming partial results | Yield results as each call completes instead of batch return | P2 |
| Dynamic `PARALLEL_SAFE` | `@tool(parallel_safe=True)` decorator metadata instead of hardcoded frozenset | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **ProcessPoolExecutor** | `ThreadPoolExecutor` is sufficient for I/O-bound tools. Process overhead is wasteful for short-lived calls. | Skip |
| 2 | **Asyncio rewrite** | `ThreadPoolExecutor` works fine. Asyncio would require rewriting all tool signatures to `async`. | Skip |
| 3 | **Auto-retry failed calls** | Individual tools should handle their own retry logic. Parallel layer should not mask transient failures. | Skip |
| 4 | **Result deduplication** | Not a common use case. Callers can deduplicate if needed. | Skip |
| 5 | **Cross-call dependency graph** | Would require a DAG scheduler. Use sequential calls or a workflow engine instead. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
