<- Back to [Workflow Overview](../WORKFLOW.md)

# 🗺️ Changelog

## 📝 Version History

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

*(No breaking changes recorded for pre-v1. Add here as they occur.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Strict type validation | ✅ Pre-v1 | `VALID_WORKFLOWS` frozenset prevents LLM hallucination |
| Fail-fast parameter guards | ✅ Pre-v1 | Autocode validates `target_file`, `error_msg`, `feature_desc` before git snapshots |
| Guaranteed observability | ✅ Pre-v1 | Every response contains `trace_id`. Auto-generated if not provided |
| Auto-routing | ✅ Pre-v1 | `type="auto"` uses Router to classify goal and select workflow |
| Router confidence guard | ✅ Pre-v1 | Low-confidence routing aborts with clarifying questions |
| Resume support | ✅ Pre-v1 | `resume=True` continues interrupted workflows from checkpoint |
| Understand workflow | ✅ Pre-v1 | Codebase Knowledge Graph builder with `project_root` parameter |
| Lazy router import | ✅ Pre-v1 | `core.router` imported inside `auto` branch to prevent circular deps |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `@meta_tool` refactor | Add `action` param with `Literal` validation and auto-generated schema. Rename `type` to `action`. | P0 |
| Un-multiplex | Extract workflow-specific validation into atomic handlers under `workflow_ops/actions/` (follow `browser_ops/actions/` pattern) | P0 |
| Test restructure | Add `conftest.py`, split `test_workflow.py` into per-concern files: validation, autocode params, understand params, auto-routing, execution, trace_id, integration | P1 |
| `understand` in `WorkflowType` Literal | Add `"understand"` to the `WorkflowType` Literal to match `VALID_WORKFLOWS` | P1 |
| Per-workflow timeout | `timeout` parameter for long-running workflows | P2 |
| Workflow cancellation | Graceful cancellation with checkpoint save | P2 |
| Progress streaming | Yield intermediate results for long workflows | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Nested workflows** | `workflow → workflow` creates complexity. Use sequential calls or sub-workflows instead. | Skip |
| 2 | **Workflow composition** | Chaining workflows (research → report) is better handled by the Planner, not the tool facade. | Skip |
| 3 | **Dynamic workflow registration** | `VALID_WORKFLOWS` is explicit by design. Dynamic registration risks LLM hallucination. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
