<- Back to [Workflow Overview](../WORKFLOW.md)

# 🛡️ AI Instructions

> **v1.0 — `@meta_tool` refactor with two-level dispatch.** These rules govern how AI agents (and humans) edit the workflow tool. Read them BEFORE making any change to `tools/workflow.py`, `tools/workflow_ops/`, or the test suite.

## ❌ NEVER DO

1. **Never call `workflows.base.run_workflow()` directly from the facade** — The facade is a thin router. The single entry point to `run_workflow()` is `helpers._execute_workflow()`. Type handlers call `_execute_workflow()`; the facade calls type handlers via the `run` action handler. Bypassing this chain breaks trace_id guarantee, kwargs conditioning, and the workflow_type metadata.
2. **Never add a workflow type without `@register_type`** — Every type handler in `tools/workflow_ops/types/` MUST be decorated with `@register_type("<type_name>", help_text="...")`. Without the decorator, the type isn't in `TYPE_DISPATCH` and `workflow(action="run", type="<new_type>")` returns "Invalid workflow type".
3. **Never add an action without `@register_action`** — Every action handler in `tools/workflow_ops/actions/` MUST be decorated with `@register_action("workflow", "<action_name>", help_text=..., examples=[...])`. Without the decorator, the action isn't in `DISPATCH` and `@meta_tool` won't include it in the `Literal[...]` enum.
4. **Never validate type-specific params in the facade** — Type-specific validation (e.g. autocode's `target_file`, understand's `project_root`) lives in the type handler, NOT in `tools/workflow.py` or `actions/run.py`. The `run` action handler only validates that `type` is non-empty and registered — it forwards ALL params to the type handler, which does its own validation. Co-locating validation with the type keeps the `run` action thin and makes adding a new type a self-contained change.
5. **Never replace `_make_error()` with `fail()`** — The workflow tool's error contract requires `trace_id` on EVERY response, including errors from early validation. `fail()` from `registry.py` doesn't include `trace_id`. The workflow tool also returns `status="error"` (not `"failed"`) for backwards compat with existing JSONL log analyzers. Every error path goes through `_make_error(error, trace_id, **extra)`.
6. **Never remove the `trace_id` guarantee** — Every response must contain `trace_id`. `_ensure_trace_id()` is called by every type handler — auto-generates one if the caller didn't provide it. Even early validation failures are logged with a `trace_id`.
7. **Never remove fail-fast parameter guards** — Autocode validates `target_file`, `error_msg`, `feature_desc` BEFORE any filesystem mutation (git snapshots). The guards live in `types/autocode.py`.
8. **Never remove the router confidence guard** — Low-confidence auto-routing must abort with `needs_clarification` status, not proceed blindly. The guard lives in `types/auto.py` and fires EVEN IF `clarifying_questions` is empty (Bug #6 fix).
9. **Never rename `type` to `workflow_type`** — The `type` param name is KEPT (v1.0 design decision). The breaking change was additive (`action="run"` prefix); renaming `type` would be a second breaking change with no functional benefit. See [CHANGELOG.md § Deferred](CHANGELOG.md#-deferred--out-of-scope).
10. **Never remove auto-discovery from `actions/__init__.py` or `types/__init__.py`** — Both `__init__.py` files use `Path.glob("*.py")` to import every `.py` file (except `__init__.py` itself), triggering the `@register_action` / `@register_type` decorators. Hardcoding imports would create a maintenance footgun (forgetting to add a new file = silent omission from `DISPATCH` / `TYPE_DISPATCH`).
11. **Never add `**kwargs` to the `@tool` facade signature** — FastMCP derives the schema from the signature. `**kwargs` produces an opaque blob — all parameter documentation is lost. Type handlers and action handlers MAY use `**kwargs` internally (they pick what they need), but the facade MUST list every param explicitly.
12. **Never use `tool` as a variable name** in facade or action files — shadows the `@tool` decorator from `registry.py`, causing `NameError` at decoration time.
13. **Never remove the lazy router import** — `core.router` MUST stay inside `types/auto.py`'s `_type_auto()` body, NOT at module top. Importing it at module load time creates a circular dependency.
14. **Never print to stdout** — MCP stdio corruption. Return dicts only.
15. **Never create `.bak` files** — forbidden by project rules.
16. **Never rewrite the entire file** when editing — surgical edits only. Preserve existing code exactly.
17. **Never skip `compileall` before `pytest`** — catches syntax errors early.
18. **Never forget the decorator order: `@tool` (outer) → `@meta_tool` (inner)** — `@meta_tool` mutates `__annotations__` and `__doc__` in place. If `@tool` ran first, it would mark the un-mutated function. `@tool` returns `fn` unchanged (just sets `_is_mcp_tool = True`), so the order works because `@meta_tool` then mutates the same `fn` object.
19. **Never assume `DISPATCH` is populated when `@meta_tool` runs** — the facade's `from tools import workflow_ops  # noqa: F401` import MUST appear BEFORE the `@meta_tool` decorator. `workflow_ops/__init__.py` triggers the auto-discovery that populates `DISPATCH`. If `@meta_tool` runs first, it raises `ValueError("@meta_tool received empty dispatch...")`.
20. **Never add workflow to `PARALLEL_SAFE`** — workflows are long-running blocking calls. The facade's docstring explicitly notes "Do NOT add to PARALLEL_SAFE". Nesting workflow inside `parallel()` would deadlock or starve the executor.

## ✅ ALWAYS DO

21. **Always use `@meta_tool` on the facade** — Auto-generates the `action: Literal[...]` enum from `DISPATCH`. Don't hand-write the `Literal[...]` — it will drift from `DISPATCH` as actions are added/removed.
22. **Always register new types via `@register_type("<name>", help_text="...")`** — drops into `tools/workflow_ops/types/<name>.py`. Auto-discovered by `types/__init__.py`. No edits to the facade needed.
23. **Always register new actions via `@register_action("workflow", "<name>", help_text=..., examples=[...])`** — drops into `tools/workflow_ops/actions/<name>.py`. Auto-discovered by `actions/__init__.py`. No edits to the facade needed.
24. **Always validate type-specific params in the type handler** — co-locate validation with the type's other logic. Use `_validate_goal()`, `_ensure_trace_id()`, `_make_error()` from `helpers.py`.
25. **Always call `_execute_workflow()` from type handlers** — it's the SINGLE entry point to `workflows.base.run_workflow()`. It builds kwargs conditionally per type and guarantees `trace_id` in the result.
26. **Always forward `files` / `git_diff` / `dry_run` only when non-empty/`True`** — matches the legacy "don't forward empty defaults" behavior. `_execute_workflow()` already does this for the autocode type — don't change it.
27. **Always test the kill-switch paths** — missing `action`, unknown `action`, missing `type` for `run`, invalid `type`, missing `goal`, missing autocode params (`target_file`/`error_msg`/`feature_desc`), missing understand `project_root`, missing autoresearch `target_file`.
28. **Always test auto-routing** — `direct` outcome, `low` confidence outcome (with AND without `clarifying_questions`), success outcome, router exception.
29. **Always test `trace_id` propagation** — auto-generation when not provided, preservation when provided, presence in EVERY response (including errors).
30. **Always test execution failure** — mock `run_workflow` with `side_effect=Exception` and verify the error response includes `trace_id` + `duration_ms`.
31. **Always include `valid_types` in `type` validation errors** — helps the LLM correct itself. `_action_run` already does this.
32. **Always patch `tracer` in ALL THREE modules** when testing — `tools.workflow.tracer`, `tools.workflow_ops.helpers.tracer`, `tools.workflow_ops.types.auto.tracer`. Python's `from core.tracer import tracer` creates a local binding at import time; patching `core.tracer.tracer` after import doesn't affect existing bindings. Use `ExitStack` in the `mock_tracer` fixture. (See `tests/tools/workflow/conftest.py`.)
33. **Always update this doc + API.md + ARCHITECTURE.md + CHANGELOG.md** when adding actions, adding types, changing parameters, or modifying routing logic.
34. **Always update the `doc_sections` list in the facade** when adding an action — the `| Need | Action | Why |` table in the docstring helps the LLM pick the right action.
35. **Always sort `DISPATCH` keys when generating error messages** — `sorted(dispatch.keys())` produces a deterministic `"cancel | history | list | run | status"` ordering. Don't rely on dict insertion order.

---

## 🚫 Anti-Patterns & Lessons Learned

> ### v1.0: Two-level dispatch (action + type) instead of a single `type` param
> - **What happened:** Pre-v1 used a single `type` param that did double duty — it was both "what kind of workflow to run" AND implicitly "the action is run-a-workflow" (because there was no other action). Status, history, cancel were either nonexistent or hacked in via special `type` values.
> - **Why it matters:** Adding `list` / `status` / `cancel` / `history` as first-class actions required either (a) polluting the `type` namespace with non-workflow-type values like `type="status"`, or (b) introducing a real second dispatch dimension. Option (b) is cleaner: `action` (meta) + `type` (workflow).
> - **Fix:** v1.0 introduced `action` as the META-level dispatch and kept `type` as the WORKFLOW-TYPE-level dispatch. Only `action="run"` uses `type`. The breaking change is additive: callers prepend `action="run",` to existing `workflow(type=...)` calls. The `type` param name was KEPT (not renamed) to minimize call-site churn.

> ### v1.0: `@meta_tool` auto-generates the `action: Literal[...]` enum
> - **What happened:** Pre-v1 hand-wrote `WorkflowType = Literal["research", "data", "autocode", ...]` at the top of `workflow.py`. Every time a type was added, three places needed updating: `VALID_WORKFLOWS` frozenset, `WorkflowType` Literal, and the docstring. They drifted — `deep_research` was missing from all three (Pre-v1.2 bug), `understand` was missing from the Literal only (Pre-v1.1 bug #4).
> - **Why it matters:** Hand-maintained parallel lists of the same information always drift. The Literal is the LLM-facing schema; if it's missing a type, the LLM can't invoke that type.
> - **Fix:** v1.0 replaced both `VALID_WORKFLOWS` and `WorkflowType` with `TYPE_DISPATCH` (a single registry populated by `@register_type` decorators). `@meta_tool` reads `DISPATCH` and auto-generates the `action: Literal[...]` enum. Adding a type now requires editing exactly ONE place: the new `types/<name>.py` file.

> ### v1.0: Validation moved from facade to type handlers
> - **What happened:** Pre-v1 had a 100-line if/elif chain in the facade that validated `target_file` for autocode, `project_root` for understand, `error_msg`/`feature_desc` for autocode modes, etc. — all inline.
> - **Why it matters:** The facade became a 263-line monolith. Adding a new workflow type meant editing the facade (validation branch + execution branch), which is exactly the kind of multiplexed dispatch the `@meta_tool` pattern was designed to eliminate.
> - **Fix:** v1.0 moved all type-specific validation into `types/<name>.py` handlers. The `run` action handler (`actions/run.py`) is intentionally thin: it validates `type` is non-empty + registered, then forwards ALL params to the type handler. The type handler does its own validation and calls `_execute_workflow()`. Adding a new type is now a self-contained change to ONE new file.

> ### Pre-v1.2: `report` listed in `VALID_WORKFLOWS` but no `report` workflow existed
> - **What happened:** `report` was listed in `VALID_WORKFLOWS` but no `report` workflow existed — `run_workflow()` returned "Unknown workflow type" when the LLM called `workflow(type="report")`.
> - **Why it matters:** The LLM would attempt to use `workflow(type="report")` based on the docstring, waste a turn, and get a confusing error. Report generation is a tool (`report(action="...")`), not a workflow.
> - **Fix:** Removed `report` from `VALID_WORKFLOWS`, `WorkflowType` Literal, and docstring. In v1.0, the equivalent is: `report` is NOT in `TYPE_DISPATCH` (no `types/report.py` file exists). The `report` tool is called directly when needed.

> ### Pre-v1.2: `deep_research` missing from `VALID_WORKFLOWS`
> - **What happened:** `deep_research` workflow existed and `run_workflow()` handled it, but it was missing from `VALID_WORKFLOWS` — the LLM couldn't invoke it directly, only via `type="auto"` routing.
> - **Why it matters:** Users couldn't explicitly request deep research; they had to hope the router would pick it. For known-complex research tasks, explicit invocation is better.
> - **Fix:** Added `deep_research` to `VALID_WORKFLOWS`, `WorkflowType` Literal, and docstring. In v1.0, the equivalent is: `types/deep_research.py` exists and registers itself via `@register_type("deep_research")`.

> ### Pre-v1.1 #3: `understand` workflow validated `project_root` but never forwarded it
> - **What happened:** The Pre-v1 facade validated `project_root` was non-empty for `type="understand"`, then forgot to pass it to `run_workflow()`. Understand defaulted to the agent root directory instead of the user-specified project directory.
> - **Why it matters:** Silent data loss — the validation passed but the parameter was dropped. The workflow ran on the wrong codebase.
> - **Fix:** Forwarded `project_root` to `run_workflow()`. In v1.0, the fix lives in `helpers._execute_workflow()` (the `elif wf_type == "understand": run_kwargs["project_root"] = ...` branch) — centralizing the kwargs-building so this class of bug can't recur in a new type handler.

> ### Pre-v1.1 #6: Auto-routing low-confidence guard only aborted if `clarifying_questions` was non-empty
> - **What happened:** The guard checked `if decision.confidence == "low" and decision.clarifying_questions:` — the `and` short-circuited when questions were empty/None, falling through to execution.
> - **Why it matters:** The guard's purpose is to prevent wasting 15+ minutes on misunderstood tasks. Empty questions shouldn't bypass that protection.
> - **Fix:** Abort on low confidence REGARDLESS of whether questions exist. Provide a default question ("Please provide more details about what you want to achieve.") when none were given. In v1.0, the fix lives in `types/auto.py`'s `_type_auto()`.

> ### v1.0: `mock_tracer` fixture must patch THREE modules
> - **What happened:** The first version of `conftest.py` patched only `core.tracer.tracer`. Tests that depended on `tracer.error()` being called (validation failure tests) failed because `tools.workflow_ops.helpers.tracer` and `tools.workflow_ops.types.auto.tracer` were still bound to the real tracer.
> - **Why it matters:** Python's `from core.tracer import tracer` creates a local binding to the tracer OBJECT at import time. Patching `core.tracer.tracer` after import doesn't affect existing bindings — each module that did the `from ... import` has its own `tracer` name.
> - **Fix:** `mock_tracer` uses `ExitStack` to patch `tracer` in all three modules: `tools.workflow.tracer`, `tools.workflow_ops.helpers.tracer`, `tools.workflow_ops.types.auto.tracer`. Same pitfall documented as Anti-Pattern #1 in consult-v1.0-staging and vision-v1.0-staging (the `_call_vision` indirection).

> ### v1.0: `cancel` action catches `ImportError` separately
> - **What happened:** The first version of `cancel.py` used a single `try/except Exception` around `request_cancellation()`. When autocode wasn't installed, the `ImportError` was caught and returned as an error — but the user couldn't tell whether cancellation failed or autocode was just missing.
> - **Why it matters:** A deployment without autocode installed should still be able to call `cancel` without an error status — it's a valid deployment configuration, not a failure.
> - **Fix:** Catch `ImportError` separately from other exceptions. Return success with a "no cancellation mechanism is available in this deployment" message. Other exceptions still return error.

---

*Last updated: 2026-07-15 (v1.0). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [CHANGELOG.md](CHANGELOG.md) for version history.*
