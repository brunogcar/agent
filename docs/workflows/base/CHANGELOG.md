<- Back to [Base Overview](../BASE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Status |
|---------|------|--------|
| v1.3 | 2026-07-08 | **Chonkie-aware `trim_state()`:** When chonkie is available, splits oversized fields into sentence-aware chunks and evicts each individually (precise recall later). Keeps first chunk as preview in state. Falls back to whole-string eviction (v1.0 behavior) if chonkie is missing or chunking fails. New `_evict_field()` helper. Tests updated to mock `_chunk_text` for deterministic path control. **Note:** `trim_state()` is currently a utility — no workflow calls it yet (#18 tracks wiring it in). |
| v1.2 | 2026-07-06 | **Checkpoint + state fixes:** `node_error` now saves full state (not just `{status, error}`) for resume (#1). Exception handler saves checkpoint before returning failure (#2). `node_done` saves success checkpoint before `mark_complete` (#7). Resume no longer clobbers checkpoint's original goal (#5). `task` field added to `WorkflowState` TypedDict (#4). Module docstring fixed ("three workflows" → six). `@meta_tool` adoption noted for notify (#8 — deferred). Test restructure: split into `test_node_helpers` + `test_dispatcher` + `test_trim_state` + `conftest` (#9). |
| v1.1 | 2026-07-05 | Bugfix batch in `workflows/helpers/checkpoint.py`: docstring path corrected (#15); `resume_count` computed via JSON parsing instead of string-matching (#16). `report` removed from `VALID_WORKFLOWS`. `deep_research` added. Error message updated to list all 5 types. |
| v1.0 | — | Released — Shared `WorkflowState`, node helpers (`node_step`/`node_error`/`node_done`), `trim_state()`, `run_workflow()` dispatcher, checkpoint resumption, trace lifecycle. |

---

## ⚠️ Breaking Changes

### v1.2 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| `node_error` saves full state checkpoint | Was saving only `{status, error}`. Resume from error now has full context. | No migration — strictly better. |
| Exception handler saves checkpoint | Was: crash = no checkpoint. Now: crash = checkpoint saved. | No migration. |
| `node_done` saves success checkpoint | Was: no checkpoint on success (only `mark_complete` which deletes). Now: checkpoint saved first, then deleted. | No migration. |
| Resume preserves checkpoint's goal | Was: `{**restored, "goal": goal}` overwrote original. Now: `{**restored}` keeps original. | No migration — if you pass a different goal on resume, it's ignored (correct behavior). |
| `task` field added to `WorkflowState` | Was: set at runtime but not declared in TypedDict. Now: declared. | No migration. |

### v1.1 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| `resume_count` computed via JSON parsing | More accurate — no false positives from string-matching. | No migration. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Shared `WorkflowState` TypedDict | ✅ v1.0 | All six workflows share this base schema |
| `node_step()` trace logging | ✅ v1.0 | Side-effect helper, returns None (not a LangGraph node) |
| `node_error()` error handling | ✅ v1.0 | Guard against empty messages, saves checkpoint |
| `node_done()` completion | ✅ v1.0 | Finishes trace, marks complete |
| `trim_state()` memory eviction | ✅ v1.0 | Phase 5: evicts oversized fields to async queue. v1.3: chonkie-aware (chunked eviction + preview, fallback to whole-string). |
| `run_workflow()` dispatcher | ✅ v1.0 | Routes to 6 workflow types, trace auto-creation |
| Checkpoint resumption | ✅ v1.0 | `resume=True` restores from journal, version validation |
| Autocode compatibility | ✅ v1.0 | Converts `goal` → `task` for autocode workflow |
| Understand standard routing | ✅ v1.0 | Routed through `graph.invoke()` like all other workflows |
| Exception isolation | ✅ v1.0 | Try/except wrapper, clean failure dicts |
| LangGraph immutability | ✅ v1.0 | Partial update dicts, no in-place mutation |
| `report` removed from workflows | ✅ v1.1 | `report` is a tool, not a workflow |
| `deep_research` added to dispatcher | ✅ v1.1 | Was handled but missing from valid types list |
| Error message lists all types | ✅ v1.1 | Was stale (`research \| data \| autocode`) |
| Checkpoint `resume_count` JSON parsing | ✅ v1.1 | Was string-matching, now JSON parse |
| #1 `node_error` full state checkpoint | ✅ v1.2 | Was: `{status, error}` only. Now: full state for resume. |
| #2 Exception handler checkpoint | ✅ v1.2 | Was: no checkpoint on crash. Now: checkpoint saved. |
| #3 Understand trace/checkpoint | ✅ v1.2 | trace_id injected (v1.0). Checkpoints: understand nodes use `tracer.step()` directly (by design — they have their own `UnderstandState`, not `WorkflowState`). |
| #4 `task` field in `WorkflowState` | ✅ v1.2 | Was: set at runtime but undeclared. Now: declared. |
| #5 Resume goal overwrite | ✅ v1.2 | Was: `{**restored, "goal": goal}`. Now: `{**restored}`. |
| #6 `node_step()` returns None | ✅ v1.2 | False positive — `node_step` is a helper, not a LangGraph node. INSTRUCTIONS.md rule corrected. |
| #7 `node_done()` success checkpoint | ✅ v1.2 | Was: no checkpoint. Now: saved before `mark_complete`. |
| #8 `@meta_tool` on notify | ✅ v1.2 | Deferred — `notify` is a simple `@tool` (no dispatch table). Will adopt `@meta_tool` when notify is refactored. |
| #9 Test restructure | ✅ v1.2 | Split into `test_node_helpers` + `test_dispatcher` + `test_trim_state` + `conftest`. |
| #17 Chonkie-aware `trim_state()` | ✅ v1.3 | Chunked eviction + preview (fallback to v1.0 whole-string if chonkie missing). Tests mock `_chunk_text` for deterministic path control. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 10 | **Configurable eviction threshold** | Hardcoded `len(val) // 4 > 1000`. Make configurable via `.env` | P2 |
| 11 | **Configurable evicted fields** | Hardcoded `["search_results", "output", "analysis"]`. Make configurable | P2 |
| 12 | **Workflow registration** | Replace hardcoded if/elif dispatch with dynamic registry (e.g., `WORKFLOW_REGISTRY` dict) | P2 |
| 13 | **Input validation** | Add `run_workflow()` input validation (non-empty goal, valid workflow_type) | P2 |
| 14 | **Timeout wrapper** | Add configurable timeout around `graph.invoke()` to prevent hung workflows | P2 |
| 15 | **Result pruning** | Pipe `result` through `prune_tool_dict()` before return to prevent oversized outputs | P3 |
| 16 | **Parallel workflow dispatch** | Evaluate `asyncio.gather()` for parallel workflow execution | P3 |
| 18 | **Wire `trim_state()` into workflow graphs** | `trim_state()` is a utility (v1.3: chonkie-aware) but no workflow calls it. Wire it into graphs between nodes that produce large outputs (e.g., after `search_results` is populated, before the next node runs). This is the real gap — the chonkie improvement is "ready for use," not "in use." | P1 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove checkpoint system** | Checkpoints are essential for resumability and debugging. | Skip |
| 2 | **Remove trace auto-creation** | Trace IDs are required for observability. | Skip |
| 3 | **Store full state in checkpoints** | `trim_state()` already prevents bloat. Full state is now saved on error/done (v1.2). | Skip |
| 4 | **Synchronous-only workflows** | All workflows are sync since v1.0. | Skip |
| 5 | **Workflow composition** | Running workflows inside workflows would create complex state management. Use sequential calls instead. | Skip |

---

*Last updated: 2026-07-06 (v1.2). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for utility signatures, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
