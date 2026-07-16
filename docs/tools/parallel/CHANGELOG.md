<- Back to [Parallel Overview](../PARALLEL.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.0** | 2026-07-15 | `@meta_tool` refactor: 3 actions (`run`/`race`/`pipeline`), `parallel_ops/` subpackage (8 files), breaking `tools`→`tasks` param rename, new `action`+`timeout` params, `PARALLEL_SAFE` expanded 6→10, `_TOOL_MAP` expanded to 17 tools. 93 tests across 7 files. Old `test_parallel.py` deleted. `core/parallel_executor.py` is now a backwards-compat shim. |
| Pre-v1 | 2026-07-03 | Initial parallel tool: single `parallel(tools, ...)` facade, `ThreadPoolExecutor`, real global timeout via `wait()`, nested-call guard, `PARALLEL_SAFE` allowlist (6 tools), explicit `_TOOL_MAP` (8 entries). 15 tests in one `test_parallel.py`. |

---

## ⚠️ Breaking Changes

| Version | Change | Migration |
|---------|--------|-----------|
| **v1.0** | Param `tools` renamed to `tasks`. Legacy `parallel(tools=[...])` fails FastMCP schema validation with `TypeError` (unknown kwarg `tools`). | Update callers to `parallel(action="run", tasks=[...])`. The `action` param is now required. The router heuristic that routes to `parallel` for parallel intent is unchanged — only the LLM-visible call signature changed. Update `docs/system_prompts/system_prompt.md` examples accordingly. |
| **v1.0** | `action` is now a required parameter. Legacy `parallel(tools=[...])` (no `action`) returns `{"status": "error", "error": "action is required (pipeline \| race \| run)"}`. | Pick the action that matches the intent: `run` (barrier — wait for all, pre-v1 behaviour), `race` (first success wins, cancel rest), or `pipeline` (sequential chain with result feeding). |
| **v1.0** | `core/parallel_executor.py` is now a backwards-compat shim. The function `dispatch_parallel` is now an alias for `dispatch_run`; `dispatch_race` and `dispatch_pipeline` are new. | Existing imports `from core.parallel_executor import dispatch_parallel, PARALLEL_SAFE, _parallel_depth, _safe_run` continue to work unchanged. **New code** should import from `tools.parallel_ops.executor` / `tools.parallel_ops.tool_map` directly (the shim's `__all__` lists all 9 re-exported names). |
| **v1.0** | The pre-v1 envelope key `data.completed` / `data.failed` semantics are unchanged, but every response now also includes a top-level `duration_ms` (added by the facade after the handler returns). | Pure addition — no migration needed unless callers strict-validate the response shape. |
| **v1.0** | `race` envelope status is `"success"` even when all tasks fail (the race itself completed). Callers must check `winner is not None` to distinguish "race ran" from "race produced a winner". | `if result["status"] == "success" and result["winner"] is not None: ...`. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| ThreadPoolExecutor concurrent execution | ✅ Pre-v1 | `dispatch_run` in `core/parallel_executor.py` (now in `tools/parallel_ops/executor.py`) |
| Real global timeout via `wait()` | ✅ Pre-v1 | Replaced broken `as_completed()` + `future.result()` pattern |
| Nested-call guard | ✅ Pre-v1 | `threading.local()` depth tracking via `_parallel_depth` |
| `PARALLEL_SAFE` allowlist | ✅ Pre-v1 | Expanded v1.0: 6 → 10 tools (`web`, `file`, `python`, `python_exec`, `notify`, `github`, `consult`, `vision`, `report`, `agent`) |
| `allow_unsafe` override | ✅ Pre-v1 | Bypass safety check with explicit flag |
| `max_workers` clamp (1–8) | ✅ Pre-v1 | Prevents thread pool exhaustion |
| Explicit `_TOOL_MAP` | ✅ Pre-v1 | Expanded v1.0: 9 → 17 tools, all lazy-imported. `parallel` intentionally omitted (nested-parallel guard). |
| Result/error wrapping | ✅ Pre-v1 | `{"tool": name, "status": ..., "result": ...}` per call |
| `@meta_tool` refactor | ✅ v1.0 | Facade is now a thin dispatch wrapper; `action: Literal["pipeline","race","run"]` auto-generated from `DISPATCH` |
| Un-multiplex into `parallel_ops/` | ✅ v1.0 | 8-file subpackage: `_registry.py`, `__init__.py`, `tool_map.py`, `executor.py`, `actions/{__init__,run,race,pipeline}.py` |
| 3 actions (`run` / `race` / `pipeline`) | ✅ v1.0 | `run` = barrier (wait for all, pre-v1 behaviour); `race` = first success wins (cancel rest, `as_completed`); `pipeline` = sequential chain with result feeding (NOT parallel despite the tool name) |
| Test restructure | ✅ v1.0 | 93 tests across 7 files (`conftest.py` + `test_run.py` / `test_race.py` / `test_pipeline.py` / `test_dispatch.py` / `test_tool_map.py` / `test_executor.py`). Old `test_parallel.py` deleted. |
| Per-call `timeout` override | ✅ v1.0 | `timeout=-1` (default) → `cfg.worker_timeout`; any `>=0` int → explicit per-call override. Replaces the pre-v1 P2 roadmap item ("Per-tool timeout configuration") with a simpler per-call model. |
| Backwards-compat shim | ✅ v1.0 | `core/parallel_executor.py` re-exports `dispatch_parallel` (alias), `dispatch_run`, `dispatch_race`, `dispatch_pipeline`, `PARALLEL_SAFE`, `_TOOL_MAP`, `_get_tool_fn`, `_parallel_depth`, `_safe_run`. Legacy imports continue to work. |
| Auto-discovery of actions | ✅ v1.0 | `tools/parallel_ops/__init__.py` globs `actions/*.py` and imports each via `importlib.import_module`, triggering `@register_action` decoration. Adding a 4th action = drop a new file in `actions/`, no edits to `__init__.py` needed. |
| `duration_ms` in every response | ✅ v1.0 | Facade times the handler call (`time.time()` delta) and adds `duration_ms` to the response dict. Mirrors `consult.py` / `swarm.py` pattern. |
| Pipeline "feed" mechanism | ✅ v1.0 | Per-task `feed` key (None \| str \| dict) controls how the previous result flows into the next call's args. See [API.md](API.md#-pipeline-feed-mechanism). |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Streaming partial results | Yield results as each call completes instead of batch return. Needs async — MCP stdio transport doesn't stream today; requires gateway mode (HTTP transport) in `core/llm_backend/`. *(v1.4 note: `complete_with_tools()` is now implemented for native tool calling, but streaming still requires gateway mode — these are separate features.)* | P2 |
| Dynamic `PARALLEL_SAFE` | `@tool(parallel_safe=True)` decorator metadata instead of hardcoded frozenset. Requires touching every tool module + the registry. | P3 |
| Per-tool error handling policy | Continue-on-failure vs abort-all — currently `run` always continues, `pipeline` always aborts. Make this configurable per call. | P3 |

### 💡 Suggested Roadmap (Future Sessions)

The following items are **proposed** for future parallel roadmap sessions. They are not yet committed — list them here so the next maintainer can pick the highest-value ones.

| Feature | Notes | Priority |
|---------|-------|----------|
| `parallel(action="batch")` | Batch with shared context — all tasks receive the same `args` base, with per-task overrides merged in. Reduces payload size when N tasks share 80% of their args. | P2 |
| `parallel(action="map_reduce")` | Split data across tools (map), then merge results via a reducer callable (reduce). Natural fit for chunked analysis (e.g. 10 files → 10 file reads → 1 agent synthesis). | P2 |
| `parallel(action="dag")` | Dependency graph scheduler — declare task dependencies as edges, scheduler runs independent nodes in parallel and dependent ones in order. Strict superset of `pipeline` (which is a linear DAG). | P3 |
| Streaming partial results *(deduplicated)* | Yield results as completed (needs async). Listed in the In Progress table above — kept here for visibility because it's the most-requested follow-up. | P2 |
| Dynamic `PARALLEL_SAFE` *(deduplicated)* | `@tool(parallel_safe=True)` decorator metadata. Listed above — kept here so future maintainers don't re-suggest it. | P3 |
| Per-tool error handling — continue on failure vs abort all | Currently `run` always continues and `pipeline` always aborts on first failure. Make this a per-call policy (`on_error: "continue" \| "abort"`). | P3 |
| Result aggregation — merge results from multiple tools into a single summary | Optional `aggregate` callable that receives all `results` and returns a merged dict. Useful for fan-out + summarise patterns (e.g. 3 web searches → 1 deduped list). | P2 |
| Cross-call context sharing — pass results between parallel calls | Distinct from `pipeline`'s linear feed: allow arbitrary task N to reference task M's result by name. Generalises the feed mechanism. Overlaps with `dag` action — pick one. | P3 |
| Priority scheduling — execute high-priority calls first | `max_workers` slots fill in submission order today. Add a `priority` field to task specs so high-priority tasks jump the queue. Only matters when `max_workers < len(tasks)`. | P3 |
| `parallel(action="retry")` | Retry failed calls with different tools (e.g. primary web → fallback tavily). Distinct from `race` (which fires all at once); retry is sequential with a fallback chain. | P3 |

> **Note for future maintainers:** items in the table above are *suggestions* gathered during v1.0 docs work. Before implementing any of them, re-check the current source (`tools/parallel_ops/`) and the test layout (`tests/tools/parallel/`) to confirm the refactor surface. The `dag`, `map_reduce`, and `batch` actions in particular would each warrant their own dispatch engine in `executor.py`.

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **ProcessPoolExecutor** | `ThreadPoolExecutor` is sufficient for I/O-bound tools. Process overhead is wasteful for short-lived calls. | Skip |
| 2 | **Asyncio rewrite** | `ThreadPoolExecutor` works fine. Asyncio would require rewriting all tool signatures to `async`. | Skip |
| 3 | **Auto-retry failed calls** | Individual tools should handle their own retry logic. Parallel layer should not mask transient failures. (The proposed `action="retry"` in the Roadmap above is a *different* feature — explicit fallback chain, not transparent retry.) | Skip |
| 4 | **Result deduplication** | Not a common use case. Callers can deduplicate if needed. (The proposed `aggregate` callable in the Roadmap above is the opt-in path for callers that want this.) | Skip |
| 5 | **Per-tool timeout dict** (`timeout={"web": 10, "python": 60}`) | Replaced in v1.0 by a simpler per-call `timeout: int` (applies to the whole execution). Per-tool granularity was over-engineered — the global deadline is what matters for parallel workloads. | Skip (superseded by v1.0 `timeout` param) |

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
