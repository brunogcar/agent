<- Back to [Workflow Overview](../WORKFLOW.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| Pre-v1.2 | 2026-07-05 | Added `deep_research` to `VALID_WORKFLOWS`, `WorkflowType` Literal, and docstring (was missing — LLM couldn't invoke directly). Removed `report` from all three (no `report` workflow exists — it's a tool, not a workflow). |
| Pre-v1.1 | 2026-07-05 | Bugfix batch: `WorkflowType` Literal now includes `understand` (#4); docstring lists `understand` for LLM discovery (#5); `understand` workflow now forwards `project_root` to `run_workflow` (#3); auto-routing low-confidence guard now aborts even when `clarifying_questions` is empty (#6). |

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

### Pre-v1.2 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| Removed `report` from `VALID_WORKFLOWS` | `workflow(type="report")` now returns "Invalid workflow type" instead of reaching `run_workflow()` and failing there. | Use the `report` tool directly: `report(action="dashboard", ...)` instead of `workflow(type="report")`. |
| Added `deep_research` to `VALID_WORKFLOWS` | LLM can now invoke deep research directly via `workflow(type="deep_research")`. Previously only reachable via `type="auto"` routing. | No migration — additive. |

### Pre-v1.1 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| Auto-routing low-confidence guard now aborts even with empty `clarifying_questions` | Previously, low confidence + empty questions fell through to execution. Now always aborts with `needs_clarification` status and provides a default question if none were given. | No migration — strictly safer behavior. Callers that handled `needs_clarification` still work; callers that relied on the fallthrough bug will now see the abort (correct behavior). |
| `understand` workflow now forwards `project_root` to `run_workflow` | Previously `project_root` was validated but never forwarded — understand defaulted to agent root. Now correctly passes the specified project directory. | No migration — strictly better behavior. |

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
