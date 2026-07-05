<- Back to [Base Overview](../BASE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| Pre-v1.1 | 2026-07-05 | Bugfix batch in `workflows/helpers/checkpoint.py`: docstring path corrected from `core/workflow_checkpoint.py` to `workflows/helpers/checkpoint.py` (#15); `resume_count` now computed via JSON parsing instead of string-matching `'"node": "resume"'` (#16 — was producing false positives when state fields contained that literal string). |
| Pre-Pre-v1.0 | — | Released — Shared WorkflowState, node helpers, dispatcher, checkpoint resumption, trace lifecycle |

---

## ⚠️ Breaking Changes

### Pre-v1.1 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| `resume_count` computed via JSON parsing | Previously used string-match (`'"node": "resume"' in line`) which produced false positives when a state field contained that literal string. Now parses each line as JSON and checks the `node` field. | No migration — strictly more accurate. Zombie-loop detection may fire less often (correct behavior — fewer false positives). |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Shared `WorkflowState` TypedDict | ✅ Pre-v1.0 | 22 fields, `total=False`, used by all workflows |
| `node_step()` trace logging | ✅ Pre-v1.0 | Consistent step logging with optional checkpoint |
| `node_error()` error handling | ✅ Pre-v1.0 | Guard against empty messages, saves checkpoint |
| `node_done()` completion | ✅ Pre-v1.0 | Finishes trace, marks complete |
| `trim_state()` memory eviction | ✅ Pre-v1.0 | Phase 5: evicts oversized fields to async queue |
| `run_workflow()` dispatcher | ✅ Pre-v1.0 | Routes to 5 workflow types, trace auto-creation |
| Checkpoint resumption | ✅ Pre-v1.0 | `resume=True` restores from journal, version validation |
| Autocode compatibility | ✅ Pre-v1.0 | Converts `goal` → `task` for autocode workflow |
| Understand special case | ✅ Pre-v1.0 | Direct function call instead of StateGraph |
| Exception isolation | ✅ Pre-v1.0 | Try/except wrapper, clean failure dicts |
| LangGraph immutability | ✅ Pre-v1.0 | Partial update dicts, no in-place mutation |
| `report` removed from `VALID_WORKFLOWS` | ✅ Pre-v1.1 | `report` is a tool, not a workflow — removed from `workflow_tool.py` to prevent LLM from calling `workflow(type="report")` which always failed |
| `deep_research` added to `VALID_WORKFLOWS` | ✅ Pre-v1.1 | Was handled by `run_workflow()` but missing from `VALID_WORKFLOWS` — LLM can now invoke directly |
| `run_workflow()` error message updated | ✅ Pre-v1.1 | Stale message said `Use: research \| data \| autocode` — now lists all 5 valid types |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Fix `node_error` partial checkpoint** | `node_error` saves only `{"status": "failed", "error": ...}` — loses all workflow context on resume. Should save full state. | P0 |
| 2 | **Fix exception handler missing checkpoint** | `run_workflow()` `except Exception` block returns failure dict but never calls `save_checkpoint()`. State at crash time is lost. | P0 |
| 3 | **Fix `understand` disconnect from trace/checkpoint** | `understand` workflow ignores `trace_id`, `goal`, and checkpoint system. `resume=True` is meaningless. | P0 |
| 4 | **Fix `WorkflowState` missing `task` field** | `task` is used for autocode but not declared in `WorkflowState` TypedDict. | P0 |
| 5 | **Fix resume overwriting `goal`** | `initial_state = {**restored, "status": "running", "goal": goal}` overwrites checkpoint's original goal. | P1 |
| 6 | **Fix `node_step()` returns `None`** | `node_step()` returns `None` — violates LangGraph node contract. Should return `{}` or be renamed to `_log_step()`. | P1 |
| 7 | **Fix `node_done()` no success checkpoint before complete** | `mark_complete()` may fail; success checkpoint should be saved first. | P1 |
| 8 | **`@meta_tool` refactor on tools used** | When `notify` gets `@meta_tool`, update calls in `node_done` | P1 |
| 9 | **Test restructure** | Split `test_base_nodes.py` into per-concern files + `conftest.py` | P1 |
| 10 | **Configurable eviction threshold** | Hardcoded `len(val) // 4 > 1000`. Make configurable via `.env` | P2 |
| 11 | **Configurable evicted fields** | Hardcoded `["search_results", "output", "analysis"]`. Make configurable | P2 |
| 12 | **Workflow registration** | Replace hardcoded if/elif dispatch with dynamic registry (e.g., `WORKFLOW_REGISTRY` dict) | P2 |
| 13 | **Input validation** | Add `run_workflow()` input validation (non-empty goal, valid workflow_type) | P2 |
| 14 | **Timeout wrapper** | Add configurable timeout around `graph.invoke()` to prevent hung workflows | P2 |
| 15 | **Result pruning** | Pipe `result` through `prune_tool_dict()` before return to prevent oversized outputs | P3 |
| 16 | **Parallel workflow dispatch** | Evaluate `asyncio.gather()` for parallel workflow execution | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove checkpoint system** | Checkpoints are essential for resumability and debugging. Removing them would break workflow reliability. | Skip |
| 2 | **Remove trace auto-creation** | Trace IDs are required for observability. Manual trace management would burden every caller. | Skip |
| 3 | **Store full state in checkpoints** | `trim_state()` already prevents bloat. Full state storage would be wasteful. | Skip |
| 4 | **Synchronous-only workflows** | Async workflows (understand) need special handling. The current hybrid approach is correct. | Skip |
| 5 | **Workflow composition** | Running workflows inside workflows (e.g., `research` → `autocode`) would create complex state management. Use sequential calls instead. | Skip |

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for utility signatures, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
