<- Back to [Workflow Overview](../WORKFLOW.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|---------|---------|
| **v1.2.2** | 2026-07-22 | **autoresearch type handler forwards 3 loop-control knobs** (consumed by **autoresearch v1.11 A8** + **base v1.8**). `tools/workflow_ops/types/autoresearch.py` now accepts + forwards `reflect_interval` (was: cfg-only, not a state field pre-v1.11), `convergence_window`, + `convergence_epsilon` (were state fields but the type handler didn't forward them — per-call overrides were silently dropped). Callers can now override all 3 per-invocation via `run_workflow(reflect_interval=10, convergence_window=20, ...)` instead of only via env vars. Default values (0 / 10 / 0.001) signal "use cfg default" — backward compatible. |
| **v1.2.1** | 2026-07-26 | **Cognitive framing + compose enhancement.** (1) `autoresearch` added to `ROUTER_WORKFLOWS` (was missing — router couldn't route to autoresearch via `type='auto'`). (2) Router prompt updated with cognitive-question framing (each workflow answers a distinct question: 'What is this?' / 'What's known?' / 'What approach works best?' / 'Execute the change'). (3) `compose` steps can now reference previous step outputs via `{stepN.field}` + `{prev.field}` placeholders in goal + kwargs. (4) `docs/WORKFLOWS.md` gains a 'Cognitive Framing' section documenting the toolkit (not pipeline) model. |
| **v1.2** | 2026-07-25 | **Operator UX: resume + logs + templates + kill.** (1) New `action="resume"` — resume a specific trace_id or list incomplete workflows. Reads the workflow type from the checkpoint so the caller doesn't need to specify it (cleaner than `run` with `resume=True`). (2) New `action="logs"` — full step-by-step trace timeline with pagination (`limit` default 100 + `offset` default 0). Goes beyond `status` (current/last node) and `history` (recent runs) — every node entry/exit. (3) New `action="templates"` — list available workflow templates from the new `templates/` subfolder. (4) New `action="kill"` — stronger than cancel (same mechanism — Python threads can't be force-killed, but the intent + trace message differ; kill logs `tracer.warning`, cancel logs `tracer.step`). (5) `run` action learns `template` param — applies pre-set params from a template JSON file, caller params override. (6) 4 starter templates: bug-fix (autocode `fix_error`), refactor (autocode `improve`), index-codebase (understand full), index-quick (understand graph-only). New `templates/` subfolder alongside `actions/` + `types/`. 40 new tests (8 resume + 7 logs + 18 templates + 7 kill) + test_dispatch updated for 9 actions. |
| **v1.1** | 2026-07-18 | **3 P1 items.** (1) `type="compose"` — chain multiple workflows sequentially (research → data → report); passes `prev_result` + `step_results` to each step; stops on first failure. (2) Per-workflow `timeout` param — wraps `run_workflow()` in a daemon-thread deadline; on timeout saves checkpoint + returns `"timed out"` status. Autocode ignores `timeout` (uses its own `invoke_with_timeout` + `cfg.autocode_graph_timeout`). (3) Graceful cancel for ALL workflows — new `request_workflow_cancel(trace_id)` / `is_workflow_cancelled(trace_id)` in `base.py`; cancel action calls BOTH the autocode flag AND the general flag. Non-autocode workflows check the flag post-dispatch (graph.invoke is blocking). 28 new tests (12 compose + 6 timeout + 10 cancel). |
|------|---------|
| **v1.0** | 2026-07-15 | **`@meta_tool` refactor with two-level dispatch.** Facade collapsed from 263 → 174 lines; all implementation moved to `workflow_ops/` subpackage (18 files: `_registry.py`, `_type_registry.py`, `helpers.py`, `actions/` (5 files), `types/` (7 files) + 2 `__init__.py`). **Breaking change:** `type` alone no longer works — callers MUST use `action="run"` + `type="..."`. 5 actions (`run`/`list`/`status`/`cancel`/`history`), 7 workflow types (`research`/`data`/`autocode`/`deep_research`/`understand`/`autoresearch`/`auto`). New params: `files` (JSON dict of filename→content for autocode pass-through), `git_diff` (autocode v1.1.2 git-diff input mode), `dry_run` (pre-flight: validate params + routing without executing). Tests restructured: deleted old `test_workflow.py` (304 lines, 4 classes), added 11-file test suite with 98 tests (10 test files + `conftest.py`). Old `VALID_WORKFLOWS` frozenset + `WorkflowType` Literal replaced by `TYPE_DISPATCH` registry (auto-discovered via `types/__init__.py` glob). |
| Pre-v1.2 | 2026-07-05 | Added `deep_research` to `VALID_WORKFLOWS`, `WorkflowType` Literal, and docstring (was missing — LLM couldn't invoke directly). Removed `report` from all three (no `report` workflow exists — it's a tool, not a workflow). |
| Pre-v1.1 | 2026-07-05 | Bugfix batch: `WorkflowType` Literal now includes `understand` (#4); docstring lists `understand` for LLM discovery (#5); `understand` workflow now forwards `project_root` to `run_workflow` (#3); auto-routing low-confidence guard now aborts even when `clarifying_questions` is empty (#6). |

---

## ⚠️ Breaking Changes

### v1.0 — 2026-07-15

| Change | Impact | Migration |
|--------|--------|-----------|
| **`type` alone no longer works** — the `workflow(type="research", goal="...")` API is replaced by `workflow(action="run", type="research", goal="...")`. The `type` param name is KEPT (not renamed) to minimize call-site churn, but it's now a second-level dispatch key, not the primary one. | All existing `workflow(type=...)` calls return `{"status": "error", "error": "action is required (run | list | status | cancel | history)"}`. | Add `action="run"` to every existing call: `workflow(type="research", goal="X")` → `workflow(action="run", type="research", goal="X")`. The `type` param name and value stay the same. |
| `VALID_WORKFLOWS` frozenset + `WorkflowType` Literal removed | Source code no longer references these constants — replaced by `TYPE_DISPATCH` registry in `tools/workflow_ops/_type_registry.py`. | Code that imported `VALID_WORKFLOWS` from `tools/workflow` will break. Read `sorted(TYPE_DISPATCH.keys())` from `tools.workflow_ops._type_registry` instead. |
| Auto-routing no longer the default | Old API defaulted to `type="auto"` when `type` was omitted. The v1.0 facade requires `action="run"` explicitly, and the `run` action requires `type` to be non-empty (no implicit `auto` fallback). | Always pass `action="run"` AND `type="auto"` explicitly when router-classified dispatch is desired. |
| Old `test_workflow.py` deleted | 304-line monolithic test file removed. | Use the new 11-file test suite under `tests/tools/workflow/` (98 tests across `conftest.py` + 10 `test_*.py` files). See [ARCHITECTURE.md § Testing](ARCHITECTURE.md#-testing). |

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
| Strict type validation | ✅ Pre-v1 → v1.0 | `VALID_WORKFLOWS` frozenset (Pre-v1) → `TYPE_DISPATCH` registry (v1.0). Still prevents LLM hallucination — unknown types fail fast in `_action_run` with `valid_types` in the error. |
| Fail-fast parameter guards | ✅ Pre-v1 → v1.0 | Autocode still validates `target_file`, `error_msg`, `feature_desc` before git snapshots — logic moved into `types/autocode.py`. |
| Guaranteed observability | ✅ Pre-v1 → v1.0 | Every response contains `trace_id`. `_ensure_trace_id()` in `helpers.py` auto-generates one if missing — called by every type handler. |
| Auto-routing | ✅ Pre-v1 → v1.0 | `type="auto"` uses Router to classify goal and select workflow — logic moved into `types/auto.py`. |
| Router confidence guard | ✅ Pre-v1 → v1.0 | Low-confidence routing aborts with clarifying questions — still in `types/auto.py`. |
| Resume support | ✅ Pre-v1 → v1.0 | `resume=True` continues interrupted workflows from checkpoint — forwarded through `_execute_workflow()`. |
| Understand workflow | ✅ Pre-v1 → v1.0 | Codebase Knowledge Graph builder with `project_root` parameter — handler in `types/understand.py`. |
| Lazy router import | ✅ Pre-v1 → v1.0 | `core.router` imported inside `types/auto.py` `_type_auto()` body to prevent circular deps. |
| `@meta_tool` refactor | ✅ v1.0 | Facade now uses `@tool @meta_tool(DISPATCH["workflow"], ...)` — auto-generates `action: Literal["run", "list", "status", "cancel", "history"]` from `DISPATCH`. |
| Un-multiplex (two-level dispatch) | ✅ v1.0 | Per-action handlers in `actions/` + per-type handlers in `types/`. Facade is a thin 174-line router. `workflow_ops/_registry.py` (ACTION_DISPATCH) + `workflow_ops/_type_registry.py` (TYPE_DISPATCH). |
| Test restructure | ✅ v1.0 | 11-file suite (conftest.py + 10 test files), 98 tests covering: validation, autocode params, understand params, auto-routing, run dispatch, list, status, cancel, history, dispatch registry. |
| `understand` in `WorkflowType` Literal | ✅ v1.0 | Replaced by `register_type("understand")` in `types/understand.py` — type registry is the source of truth. |
| New params: `files`, `git_diff`, `dry_run` | ✅ v1.0 | Autocode v1.1.2 pass-through params forwarded to `run_workflow()` by `helpers._execute_workflow()` only when non-empty/`True`. |
| 5 actions: `run`/`list`/`status`/`cancel`/`history` | ✅ v1.0 | `run` dispatches to types; `list`/`status`/`cancel`/`history` are leaf operations on tracer/checkpoint. |
| 9 actions: `run`/`list`/`status`/`cancel`/`history` + `resume`/`logs`/`templates`/`kill` | ✅ v1.2 | v1.2 added 4 operator-UX actions. `resume` reads workflow type from checkpoint (no caller `type` needed); `logs` returns full step-by-step timeline with pagination; `templates` lists pre-configured parameter bundles; `kill` is stronger-intent cancel (same mechanism — Python threads can't be force-killed). |
| `workflow(action="run", template=...)` | ✅ v1.2 | `run` action learns `template` param — loads pre-set params from `templates/<name>.json`, caller params override template params, validates `required` params present. 4 starter templates: bug-fix, refactor, index-codebase, index-quick. |
| `templates/` subfolder | ✅ v1.2 | Pre-configured workflow parameter sets. Drops into `workflow_ops/templates/` alongside `actions/` and `types/`. Loader (`_registry.py`) scans `*.json` at import time + caches. |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| ~~`workflow(action="run", type="compose")`~~ | ✅ v1.1 — `type="compose"` with `steps=[...]` param. | ✅ Done |
| ~~Per-workflow timeout~~ | ✅ v1.1 — `timeout` param in `run_workflow()`. | ✅ Done |
| ~~Workflow cancellation — graceful cancel for ALL workflows~~ | ✅ v1.1 — `request_workflow_cancel(trace_id)` in `base.py`; cancel action calls both flags. | ✅ Done |
| ~~Workflow templates~~ | ✅ v1.2 — `templates/` subfolder + 4 starter templates (bug-fix, refactor, index-codebase, index-quick) + `templates` action + `template` param on `run`. | ✅ Done |
| ~~`workflow(action="resume")`~~ | ✅ v1.2 — separate resume action reads workflow type from checkpoint. Two modes: trace_id-specific resume OR list incomplete. | ✅ Done |
| ~~`workflow(action="logs", trace_id=...)`~~ | ✅ v1.2 — full step-by-step trace timeline with pagination (`limit` + `offset`). | ✅ Done |
| ~~`templates/` subfolder~~ | ✅ v1.2 — `workflow_ops/templates/` alongside `actions/` + `types/`. Loader scans `*.json` at import time. | ✅ Done |
| ~~`workflow(action="kill", trace_id=...)`~~ | ✅ v1.2 — stronger-intent cancel (same mechanism — Python threads can't be force-killed). Logs `tracer.warning` instead of `tracer.step`. | ✅ Done |
| Progress streaming | Yield intermediate results for long workflows. Requires MCP transport changes (currently request/response only). | P2 |
| Parallel workflows | Run multiple workflows concurrently. Requires careful thought about `PARALLEL_SAFE` semantics (workflow is currently NOT parallel-safe — long-running blocking calls). | P3 |
| Template inheritance | Templates could extend other templates (`extends: base-template`). Currently each template is standalone. | P3 |
| Template validation | Schema validation on template JSON files (e.g. ensure `type` is a registered workflow type, `required` params match type handler signature). Currently ad-hoc. | P3 |
| Workflow metrics | Per-trace metrics: token count, cost, retry count. Currently only elapsed_s is tracked. | P3 |
| Workflow artifacts | Persistent artifact storage (output files, charts, etc.) keyed by trace_id. Currently each workflow manages its own. | P3 |
| `workflow(action="compare", trace_id1=..., trace_id2=...)` | Compare two workflow runs. Useful for A/B testing prompt changes or comparing autocode runs against the same target_file. | P4 |
| `workflow(action="export", trace_id=...)` | Export workflow results as JSON/markdown. Pulls trace + checkpoint + artifacts into a single portable bundle. | P4 |
| Dynamic workflow registration | Register new workflow types at runtime (e.g. plugin workflows). Currently `TYPE_DISPATCH` is populated only at import time via `types/__init__.py` glob. | P4 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Nested workflows** | `workflow → workflow` creates complexity. Use sequential calls or sub-workflows instead. | Skip |
| 2 | **Renaming `type` to `workflow_type`** | Would break every existing call site's param name. The v1.0 breaking change is additive (`action="run"` prefix); renaming `type` would be a second breaking change with no functional benefit. The `type` param name is KEPT. | Skip |

---

*Last updated: 2026-07-22 (v1.2.2 — autoresearch type handler forwards reflect_interval + convergence_window + convergence_epsilon). See [API.md](API.md) for action details, [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
